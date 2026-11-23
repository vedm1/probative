"""`Elicitor` (PB14): the S1 agent that interviews the operator and proposes T3 evidence.

It asks in rounds. A round is up to `round_size` questions put to a person in one go: that
is one human interaction (D1). Questions come from fixed templates filled with verbatim
text (D3), chosen deterministically, and `BiasHunter` judges each filled question before a
person sees it (D2). After every answer it measures whether the graph changed, and stops
after `quiet_rounds` rounds in which nothing did. It returns a patch. It never writes the
graph and never supplies a number: each proposed `Computed` has `value=None` (I4).

Everything a person said is in `turns.jsonl`, hash-chained, so a session resumes after a
crash and replays to the same patch. Model calls are cached or logged in the session
directory, so a resume repeats none of them.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from probative.agents.contract import (
    AgentResult,
    CostRecord,
    SelfAssessment,
    TierPolicy,
    ToolCall,
)
from probative.core.evidence import Tier
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, NodeBase, Question
from probative.elicit.bias_hunter import BiasHunter, BiasHunterError, ExchangeCandidate
from probative.elicit.build import Outcome, outcome, words
from probative.elicit.challenge import VerdictCache, challenge
from probative.elicit.gain import measure, should_stop
from probative.elicit.seal import seal
from probative.elicit.select import Plan, select
from probative.elicit.session import Session
from probative.elicit.templates import fill, load_templates, topic_question
from probative.elicit.types import (
    AskedQuestion,
    ElicitorInput,
    GainReport,
    Respondent,
    Turn,
)
from probative.formulas.validator import FormulaValidator
from probative.graph_runtime.state import GraphState, RunContext
from probative.graph_runtime.tedium import Interaction
from probative.ledger.build import DIRECT  # noqa: F401  (the formula the claims name)
from probative.ledger.contradict import PairVerdict, judge_pair
from probative.ledger.normalise import normalise
from probative.llm import TokenUsage

PROVISIONAL: Final = "claim confidence constants are provisional policy (OI38)"
FINDINGS_FILE: Final = "findings.jsonl"
_SAFE: Final = re.compile(r"[^A-Za-z0-9_-]")
EXTRA_PREFLIGHT: Final = 2


class _JsonLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def add(self, doc: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, sort_keys=True) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]


@dataclass
class _Spend:
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(input_tokens=0, output_tokens=0))
    calls: int = 0

    def add(self, usage: TokenUsage) -> None:
        self.usage = TokenUsage(
            input_tokens=self.usage.input_tokens + usage.input_tokens,
            output_tokens=self.usage.output_tokens + usage.output_tokens,
        )
        self.calls += 1

    @property
    def total(self) -> int:
        return self.usage.input_tokens + self.usage.output_tokens


class _Working:
    """The graph as the session sees it: the committed graph plus what the answers so far
    would add. Rebuilt from the turns each time, so it is a pure function of them."""

    def __init__(
        self, base: Graph, session_id: str, owner: str, ctx: RunContext, spend: _Spend
    ) -> None:
        self.base = base
        self.session_id = session_id
        self.owner = owner
        self.ctx = ctx
        self.spend = spend
        self.turns: list[Turn] = []
        self.duplicates: set[int] = set()
        self.tainted: set[int] = set()
        self.contra_nodes: dict[str, NodeBase] = {}
        self.contra_edges: dict[str, Edge] = {}
        self.judged: set[str] = set()
        self.graph = base
        self.calls: list[ToolCall] = []
        # normalised, as stored: a re-stated claim differing only in whitespace is the same claim
        self._t3 = {n.text for n in base.current() if isinstance(n, Claim) and n.tier is Tier.T3}

    # -- what a turn rests on ------------------------------------------------------------

    def proposition(self, turn: Turn) -> str | None:
        node = self.base.nodes.get(turn.subject_ref)
        return node.text if isinstance(node, Claim) else None

    def about(self, turn: Turn) -> str | None:
        return (
            turn.subject_ref if isinstance(self.base.nodes.get(turn.subject_ref), Claim) else None
        )

    # -- building ------------------------------------------------------------------------

    def _rebuild(self) -> Graph:
        used = [t for t in self.turns if t.index not in self.duplicates]
        props = {t.index: self.proposition(t) for t in used}
        abouts = {t.index: self.about(t) for t in used}
        with tempfile.TemporaryDirectory() as tmp:
            sealed = seal(
                self.session_id,
                used,
                propositions=props,
                abouts=abouts,
                source_root=Path(tmp),
                owner=self.owner,
                now=self.ctx.clock(),
                tainted=frozenset(self.tainted),
            )
        nodes = [
            *sealed.nodes,
            *self.resolutions(sealed.claims_by_turn),
            *self.contra_nodes.values(),
        ]
        edges = [
            *sealed.edges,
            *self._resolution_edges(sealed.claims_by_turn),
            *self.contra_edges.values(),
        ]
        return FormulaValidator().settle(self.base.with_patch(nodes, edges))

    def resolutions(self, claims_by_turn: dict[int, str]) -> list[NodeBase]:
        out: list[NodeBase] = []
        for t in self.turns:
            if t.index in claims_by_turn and t.template_id == "resolve_open_question":
                old = self.base.nodes.get(t.subject_ref)
                if isinstance(old, Question):
                    out.append(
                        Question.make(
                            text=old.text,
                            status="resolved",
                            raised_by=old.raised_by,
                            owner=self.owner,
                            asserted_at=self.ctx.clock(),
                        )
                    )
        return out

    def _resolution_edges(self, claims_by_turn: dict[int, str]) -> list[Edge]:
        out: list[Edge] = []
        for node in self.resolutions(claims_by_turn):
            for t in self.turns:
                old = self.base.nodes.get(t.subject_ref)
                if (
                    t.index in claims_by_turn
                    and t.template_id == "resolve_open_question"
                    and isinstance(old, Question)
                    and old.text == getattr(node, "text", None)
                ):
                    out.append(
                        Edge.make(
                            type=EdgeType.SUPERSEDES,
                            src=node.id,
                            dst=old.id,
                            owner=self.owner,
                            asserted_at=self.ctx.clock(),
                            attrs={"reason": f"answered in elicitation session {self.session_id}"},
                        )
                    )
        return out

    def extend(self, new_turns: list[Turn]) -> list[GainReport]:
        reports: list[GainReport] = []
        for turn in new_turns:
            self.turns.append(turn)
            if outcome(turn) is Outcome.CLAIM:
                text = normalise(words(turn, self.proposition(turn)))
                if text in self._t3:
                    self.duplicates.add(turn.index)  # OI46: never re-state what they already said
                else:
                    self._t3.add(text)
            before = self.graph
            after = self._rebuild()
            fresh = [
                c
                for c in after.current()
                if isinstance(c, Claim)
                and c.tier is Tier.T3
                and c.id not in self.judged
                and c.id not in before.nodes
            ]
            self.judged |= {c.id for c in fresh}
            if fresh:
                nodes, edges, judged = challenge(
                    after, fresh, self._judge, self._cache, owner=self.owner, now=self.ctx.clock()
                )
                if judged:
                    self.calls.append(
                        ToolCall(name="contradiction.judge_pair", input={"pairs": str(judged)})
                    )
                if nodes or edges:
                    self.contra_nodes.update({n.id: n for n in nodes})
                    self.contra_edges.update({e.id: e for e in edges})
                    after = self._rebuild()
            reports.append(measure(before, after))
            self.graph = after
        return reports

    _cache: VerdictCache

    def _judge(self, a: Claim, b: Claim) -> PairVerdict:
        assert self.ctx.provider is not None
        verdict, usage = judge_pair(self.ctx.provider, self.ctx.model, a, b)
        self.spend.add(usage)
        return verdict


class Elicitor:
    name = "elicitor"
    input_model = ElicitorInput
    output_model = AgentResult
    tools = ()
    tier_policy = TierPolicy(allowed=frozenset({Tier.T3}))

    def __init__(
        self,
        *,
        owner: str,
        respondent: Respondent,
        params: ElicitorInput | None = None,
        session_id: str | None = None,
    ) -> None:
        self._owner = owner
        self._respondent = respondent
        self._params = params or ElicitorInput()
        self._requested = session_id
        self._session_id = ""
        self.report: dict[str, Any] = {}

    def run(self, state: GraphState, ctx: RunContext) -> AgentResult:
        if ctx.provider is None:
            raise ValueError("Elicitor needs a provider to judge questions and contradictions")
        started = time.monotonic()
        mode = state.mode.value
        # default: one session per run directory, so two runs sharing a source root never
        # seal to the same transcript name
        wanted = self._requested or f"{ctx.run_dir.name}-1"
        self._session_id = _SAFE.sub("_", wanted) or "session"
        directory = ctx.run_dir / "elicitation" / self._session_id
        session = Session(directory)
        findings_log = _JsonLog(directory / FINDINGS_FILE)
        hunter = BiasHunter(ctx.provider, ctx.model)
        spend = _Spend()
        work = _Working(state.graph, self._session_id, self._owner, ctx, spend)
        work._cache = VerdictCache(directory / "verdicts.jsonl", ctx.model)
        params = self._params
        calls: list[ToolCall] = []
        unsure: list[str] = [PROVISIONAL]

        recorded = findings_log.read()
        dropped = {r["subject_ref"] for r in recorded if r.get("action") == "dropped"}
        audited = {(r["template_id"], r["text"]) for r in recorded if r.get("action") == "passed"}

        # -- replay what a person already answered (no question is asked twice) -------------
        by_round: dict[int, list[Turn]] = {}
        for t in session.turns():
            by_round.setdefault(t.round, []).append(t)
        round_gains: list[list[GainReport]] = []
        wasted: list[str] = []
        for r in sorted(by_round):
            gains = work.extend(by_round[r])
            round_gains.append(gains)
            wasted.extend(
                t.question_text for t, g in zip(by_round[r], gains, strict=True) if g.wasted
            )
        rounds_done = session.rounds()
        stop_reason = "max_rounds"

        # -- ask new rounds -----------------------------------------------------------------
        while rounds_done < params.max_rounds:
            if should_stop(round_gains, params.quiet_rounds):
                stop_reason = "quiet"
                break
            if ctx.budget.tokens_left - spend.total - _tokens(hunter) <= 0:
                stop_reason = "token_budget"
                unsure.append("the token budget ran out before the session ended")
                break
            asked_refs = {t.subject_ref for t in work.turns} | dropped | _own_questions(work)
            plans = select(work.graph, mode=mode, asked=asked_refs, topic=params.topic)
            round_: list[AskedQuestion] = []
            attempts = 0
            index = len(work.turns)
            for plan in plans:
                if (
                    len(round_) >= params.round_size
                    or attempts >= params.round_size + EXTRA_PREFLIGHT
                ):
                    break
                attempts += 1
                asked = _fill(plan, index + len(round_))
                cand = ExchangeCandidate(id=plan.subject_ref, question=asked)
                try:
                    found = hunter.check([cand])
                except BiasHunterError as err:
                    dropped.add(plan.subject_ref)
                    findings_log.add(
                        {
                            "action": "dropped",
                            "subject_ref": plan.subject_ref,
                            "template_id": asked.template_id,
                            "text": asked.text,
                            "why": str(err),
                            "findings": [],
                        }
                    )
                    unsure.append(f"a question was not asked because it could not be judged: {err}")
                    continue
                calls.append(
                    ToolCall(name="bias_hunter.check", input={"subject_ref": plan.subject_ref})
                )
                if BiasHunter.blocked(found):
                    dropped.add(plan.subject_ref)
                    findings_log.add(
                        {
                            "action": "dropped",
                            "subject_ref": plan.subject_ref,
                            "template_id": asked.template_id,
                            "text": asked.text,
                            "findings": [f.check_id for f in found],
                        }
                    )
                    continue
                findings_log.add(
                    {
                        "action": "passed",
                        "subject_ref": plan.subject_ref,
                        "template_id": asked.template_id,
                        "text": asked.text,
                        "findings": [f.check_id for f in found],
                    }
                )
                audited.add((asked.template_id, asked.text))
                round_.append(asked)
            if not round_:
                stop_reason = "nothing_to_ask"
                break
            tick = time.monotonic()
            answers = self._respondent.answer(tuple(round_))
            if len(answers) != len(round_):
                raise ValueError("the respondent must answer every question in the round")
            for asked_q, given in zip(round_, answers, strict=True):
                if given.kind not in {o.kind for o in asked_q.options}:
                    # refused before it is saved, so a bad answer cannot brick the session
                    raise ValueError(
                        f"answer kind {given.kind.value} was not offered for {asked_q.subject_ref}"
                    )
            seconds = time.monotonic() - tick
            made = session.append_round(
                rounds_done, list(zip(round_, answers, strict=True)), asked_at=ctx.clock()
            )
            ctx.interactions.record(
                Interaction(phase=state.phase, kind="question", seconds=seconds)
            )
            gains = work.extend(made)
            round_gains.append(gains)
            wasted.extend(t.question_text for t, g in zip(made, gains, strict=True) if g.wasted)
            rounds_done += 1
        if rounds_done >= params.max_rounds and should_stop(round_gains, params.quiet_rounds):
            stop_reason = "quiet"

        # -- audit the transcript at seal ---------------------------------------------------
        for t in work.turns:
            if (t.template_id, t.question_text) in audited:
                continue
            cand = ExchangeCandidate(
                id=f"seal:{t.index}",
                question=AskedQuestion(
                    index=t.index,
                    template_id=t.template_id,
                    subject_ref=t.subject_ref,
                    text=t.question_text,
                    options=t.options,
                    evidence_kind=t.evidence_kind,
                ),
                answer=t.answer_text,
            )
            try:
                found = hunter.check([cand])
            except BiasHunterError as err:
                work.tainted.add(t.index)
                unsure.append(
                    f"turn {t.index} could not be audited, so it is not used as evidence: {err}"
                )
                continue
            if BiasHunter.blocked(found):
                work.tainted.add(t.index)
                findings_log.add(
                    {
                        "action": "tainted",
                        "subject_ref": t.subject_ref,
                        "template_id": t.template_id,
                        "text": t.question_text,
                        "findings": [f.check_id for f in found],
                    }
                )
        skew = hunter.check_session(work.turns)
        for f in skew:
            unsure.append(f.message)

        # -- the patch ----------------------------------------------------------------------
        used = [t for t in work.turns if t.index not in work.duplicates]
        sealed = seal(
            self._session_id,
            used,
            propositions={t.index: work.proposition(t) for t in used},
            abouts={t.index: work.about(t) for t in used},
            source_root=ctx.source_root,
            owner=self._owner,
            now=ctx.clock(),
            tainted=frozenset(work.tainted),
        )
        resolutions = work.resolutions(sealed.claims_by_turn)
        res_edges = work._resolution_edges(sealed.claims_by_turn)
        nodes = {n.id: n for n in (*sealed.nodes, *resolutions, *work.contra_nodes.values())}
        edges = {e.id: e for e in (*sealed.edges, *res_edges, *work.contra_edges.values())}
        for n in nodes.values():
            if isinstance(n, Question) and n.raised_by == "elicitation" and n.status == "open":
                unsure.append(f"open question: {n.text}")
        if work.duplicates:
            unsure.append(
                f"{len(work.duplicates)} answer(s) repeated a T3 claim already held; not added"
            )
        self.report = {
            "session": self._session_id,
            "rounds": rounds_done,
            "stop_reason": stop_reason,
            "questions": len(work.turns),
            "wasted": wasted,
            "duplicates": sorted(work.duplicates),
            "tainted": sorted(work.tainted),
            "dropped": sorted(dropped),
        }
        (directory).mkdir(parents=True, exist_ok=True)
        (directory / "report.json").write_text(
            json.dumps(self.report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        total = spend.usage
        return AgentResult(
            proposed_nodes=tuple(nodes[i] for i in sorted(nodes)),
            proposed_edges=tuple(edges[i] for i in sorted(edges)),
            tool_calls=tuple([*calls, *work.calls]),
            rationale=(
                f"{len(work.turns)} question(s) in {rounds_done} round(s); stopped: {stop_reason}; "
                f"{len(wasted)} changed nothing"
            ),
            self_assessment=SelfAssessment(least_sure_about=tuple(unsure)),
            cost=CostRecord(
                input_tokens=total.input_tokens + hunter.stats.usage.input_tokens,
                output_tokens=total.output_tokens + hunter.stats.usage.output_tokens,
                wall_seconds=round(time.monotonic() - started, 3),
            ),
        )


def _tokens(hunter: BiasHunter) -> int:
    return hunter.stats.usage.input_tokens + hunter.stats.usage.output_tokens


def _own_questions(work: _Working) -> set[str]:
    """Questions this session itself raised (not contradictions, which are put to the person):
    asking about them in the same session would repeat what they just said."""
    return {
        n.id
        for n in work.graph.current()
        if isinstance(n, Question)
        and n.id not in work.base.nodes
        and n.raised_by != "contradiction"
    }


def _fill(plan: Plan, index: int) -> AskedQuestion:
    if plan.template_id.startswith("topic:"):
        from probative.elicit.templates import load_topics

        return topic_question(load_topics()[plan.subject_ref], index=index)
    template = load_templates()[plan.template_id]
    kind = template.evidence_kind or plan.evidence_kind
    asked = fill(template, index=index, subject_ref=plan.subject_ref, **plan.slots)
    return asked.model_copy(update={"evidence_kind": kind})
