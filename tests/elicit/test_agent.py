"""PB14: the `Elicitor` agent end to end, with a replay respondent and a scripted provider.
No key, no network, no person (S3)."""

from __future__ import annotations

from pathlib import Path

import pytest

import probative.formulas  # noqa: F401
from probative.core.critic import Severity
from probative.core.evidence import Tier
from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, Question
from probative.core.graph.validators import validate_graph
from probative.critics.llm_judge import Verdict
from probative.elicit.agent import Elicitor
from probative.elicit.bias_hunter import JUDGED, CheckVerdict, ExchangeVerdicts
from probative.elicit.respondent import ReplayRespondent
from probative.elicit.session import Session
from probative.elicit.types import AnswerKind, Basis, ElicitorInput, RawAnswer
from probative.formulas.validator import FormulaValidator
from probative.graph_runtime.budget import BudgetView
from probative.graph_runtime.modes import Mode
from probative.graph_runtime.phases import PHASES, Phase
from probative.graph_runtime.state import GraphState, RunContext
from probative.graph_runtime.tedium import InteractionLog, TediumAuditor
from probative.ledger.contradict import PairJudgement, PairVerdict
from probative.llm import FakeProvider, TokenUsage
from tests.elicit._helpers import NOW, OWNER, claims, t1_graph

USAGE = TokenUsage(input_tokens=50, output_tokens=2)
T1 = "Approvals take three days"


def ctx(root: Path, provider: FakeProvider | None) -> RunContext:
    return RunContext(
        provider=provider,
        model="test-model",
        run_dir=root / "run1",
        source_root=root,
        clock=lambda: NOW,
        budget=BudgetView(tokens_left=200_000, seconds_left=1800.0),
        interactions=InteractionLog(root / "run1" / "interactions.jsonl"),
    )


def state(graph: Graph, mode: Mode = Mode.SOLO) -> GraphState:
    return GraphState(graph=graph, phase=Phase.P0, mode=mode, cycle=1)


def met() -> ExchangeVerdicts:
    return ExchangeVerdicts(
        judgements=[CheckVerdict(check_id=c, verdict=Verdict.MET) for c in JUDGED]
    )


def leading() -> ExchangeVerdicts:
    return ExchangeVerdicts(
        judgements=[
            CheckVerdict(
                check_id=c, verdict=Verdict.NOT_MET if c == "leading_question" else Verdict.MET
            )
            for c in JUDGED
        ]
    )


def provider(*script: object) -> FakeProvider:
    return FakeProvider(list(script), usage=USAGE)  # type: ignore[arg-type]


def observed(text: str, n: int | None = None) -> RawAnswer:
    return RawAnswer(kind=AnswerKind.OPEN, text=text, basis=Basis.OBSERVED, basis_count=n)


UNKNOWN = RawAnswer(kind=AnswerKind.UNKNOWN)
CONSISTENT = PairJudgement(verdict=PairVerdict.CONSISTENT)


@pytest.fixture
def base(tmp_path: Path) -> Graph:
    return t1_graph(tmp_path, T1)


def solo_answers() -> dict[str, RawAnswer]:
    return {
        "who_is_affected": observed("Finance leads at four clients", 4),
        "current_workaround": RawAnswer(
            kind=AnswerKind.OPEN, text="They email the approver", basis=Basis.TOLD
        ),
        "frequency": UNKNOWN,
        "known_constraint": UNKNOWN,
        T1: RawAnswer(kind=AnswerKind.CONFIRM, basis=Basis.OBSERVED),
    }


def solo_script() -> list[object]:
    # round 1: three questions judged; round 2: two questions judged, then the confirmed T1
    # claim is compared with the T1 claim it repeats
    return [met(), met(), met(), met(), met(), CONSISTENT]


def run_solo(
    root: Path, graph: Graph, *, session: str = "s1"
) -> tuple[Elicitor, object, ReplayRespondent]:
    rep = ReplayRespondent(solo_answers())
    agent = Elicitor(owner=OWNER, respondent=rep, session_id=session)
    result = agent.run(state(graph), ctx(root, provider(*solo_script())))
    return agent, result, rep


def test_a_solo_session_proposes_t3_claims_and_questions_and_commits_clean(
    tmp_path: Path, base: Graph
) -> None:
    agent, result, rep = run_solo(tmp_path, base)
    nodes = [n for n in result.proposed_nodes]  # type: ignore[attr-defined]
    t3 = [n for n in nodes if isinstance(n, Claim)]
    assert {c.text for c in t3} == {"Finance leads at four clients", "They email the approver", T1}
    assert all(c.tier is Tier.T3 for c in t3)
    assert all(c.confidence.value is None for c in t3)  # I4: the Committer computes it
    qs = [n for n in nodes if isinstance(n, Question)]
    assert len(qs) == 2 and all(q.raised_by == "elicitation" for q in qs)  # two unknowns
    # the same checks the Committer runs: structure (I1, tier match) and the formula recompute
    graph = FormulaValidator().settle(base.with_patch(result.proposed_nodes, result.proposed_edges))  # type: ignore[attr-defined]
    assert validate_graph(graph, source_root=tmp_path) == []
    assert FormulaValidator().check(graph) == []
    assert agent.report["rounds"] == 2 and agent.report["stop_reason"] == "nothing_to_ask"
    assert len(rep.asked) == 5


def test_a_session_costs_two_interactions_and_the_tedium_auditor_is_quiet(
    tmp_path: Path, base: Graph
) -> None:
    log = InteractionLog(tmp_path / "run1" / "interactions.jsonl")
    run_solo(tmp_path, base)
    entries = log.entries()
    assert [e.kind for e in entries] == ["question", "question"]
    findings = TediumAuditor().audit(entries, PHASES)
    assert [f for f in findings if f.severity is not Severity.NOTE] == []  # a note is a count


def test_every_t3_span_re_extracts_and_holds_no_question_text(tmp_path: Path, base: Graph) -> None:
    _, result, rep = run_solo(tmp_path, base)
    spans = [n for n in result.proposed_nodes if isinstance(n, EvidenceSpan)]  # type: ignore[attr-defined]
    assert spans
    questions_asked = [q.text for q in rep.asked]
    for sp in spans:
        assert not any(q in sp.text for q in questions_asked)
    # validate_graph re-extracts every span from the sealed file (I1); see the clean-commit test
    t3_sources = [n for n in result.proposed_nodes if getattr(n, "type", "") == "source"]  # type: ignore[attr-defined]
    assert t3_sources and all(s.path.startswith(".elicitation/") for s in t3_sources)


def test_unknown_makes_a_question_and_never_a_claim(tmp_path: Path, base: Graph) -> None:
    _, result, _ = run_solo(tmp_path, base)
    texts = [n.text for n in result.proposed_nodes if isinstance(n, Question)]  # type: ignore[attr-defined]
    assert any("How often does it happen" in t for t in texts)
    assert not any(isinstance(n, Claim) and "How often" in n.text for n in result.proposed_nodes)  # type: ignore[attr-defined]


def test_the_session_stops_after_two_quiet_rounds_and_reports_each_wasted_question(
    tmp_path: Path, base: Graph
) -> None:
    rep = ReplayRespondent({}, default=UNKNOWN)
    agent = Elicitor(
        owner=OWNER,
        respondent=rep,
        session_id="stall",
        params=ElicitorInput(round_size=1, max_rounds=10, quiet_rounds=2),
    )
    agent.run(state(base), ctx(tmp_path, provider(*[met()] * 10)))
    assert agent.report["rounds"] == 2 and agent.report["stop_reason"] == "quiet"
    assert len(agent.report["wasted"]) == 2
    assert len(rep.asked) == 2


def test_a_session_resumes_after_a_crash_and_replays_to_the_same_patch(
    tmp_path: Path, base: Graph
) -> None:
    class Crash(Exception):
        pass

    class Flaky(ReplayRespondent):
        def answer(self, round_):  # type: ignore[no-untyped-def]
            if len(self.asked) >= 3:
                raise Crash
            return super().answer(round_)

    first = Flaky(solo_answers())
    with pytest.raises(Crash):
        Elicitor(owner=OWNER, respondent=first, session_id="s2").run(
            state(base), ctx(tmp_path, provider(*solo_script()))
        )
    assert Session(tmp_path / "run1" / "elicitation" / "s2").rounds() == 1  # round 1 survived
    second = ReplayRespondent(solo_answers())
    # round 1 is replayed (its judge calls were logged, not repeated), so only round 2 is judged
    resumed = Elicitor(owner=OWNER, respondent=second, session_id="s2").run(
        state(base), ctx(tmp_path, provider(met(), met(), CONSISTENT))
    )
    assert [q.subject_ref for q in second.asked] == [
        "known_constraint",
        next(iter(claims(base))).id,
    ]
    other = tmp_path / "other"
    other.mkdir()
    base2 = t1_graph(other, T1)
    _, whole, _ = run_solo(other, base2, session="s2")
    assert [n.id for n in resumed.proposed_nodes] == [n.id for n in whole.proposed_nodes]  # type: ignore[attr-defined]


def test_a_contradiction_is_shown_with_the_stored_quote_and_kept(
    tmp_path: Path, base: Graph
) -> None:
    rep = ReplayRespondent(
        {
            "who_is_affected": observed("Approvals take under one day for most clients"),
            "challenge": UNKNOWN,
        },
        default=UNKNOWN,
    )
    agent = Elicitor(
        owner=OWNER,
        respondent=rep,
        session_id="c1",
        params=ElicitorInput(round_size=1, max_rounds=2, quiet_rounds=9),
    )
    contradicts = PairJudgement(verdict=PairVerdict.CONTRADICTS)
    result = agent.run(state(base), ctx(tmp_path, provider(met(), contradicts, met())))
    assert any(e.type is EdgeType.CONTRADICTS for e in result.proposed_edges)  # type: ignore[attr-defined]
    q = next(
        n
        for n in result.proposed_nodes
        if isinstance(n, Question) and n.raised_by == "contradiction"
    )  # type: ignore[attr-defined]
    stored = claims(base)[0]
    span_text = next(n.text for n in base.nodes.values() if isinstance(n, EvidenceSpan))
    assert stored.text == span_text in q.text  # the quote is the stored span, verbatim
    asked = rep.asked[1]  # round 2 puts the contradiction to the person
    assert asked.template_id == "challenge_contradiction"
    assert span_text in asked.text and "Approvals take under one day" in asked.text


def test_onboarding_asks_reconstruct_questions_only(tmp_path: Path, base: Graph) -> None:
    rep = ReplayRespondent({}, default=UNKNOWN)
    agent = Elicitor(
        owner=OWNER, respondent=rep, session_id="o1", params=ElicitorInput(max_rounds=3)
    )
    agent.run(state(base, Mode.ONBOARDING), ctx(tmp_path, provider(*[met()] * 6)))
    assert rep.asked
    assert {q.template_id for q in rep.asked} <= {
        "topic:recorded_decision",
        "reconstruct_recorded_item",
    }


def test_a_blocked_question_is_never_asked_and_is_recorded(tmp_path: Path, base: Graph) -> None:
    rep = ReplayRespondent({}, default=UNKNOWN)
    agent = Elicitor(
        owner=OWNER,
        respondent=rep,
        session_id="b1",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    agent.run(state(base), ctx(tmp_path, provider(leading(), met())))
    assert [q.subject_ref for q in rep.asked] == ["current_workaround"]  # the first was dropped
    assert "who_is_affected" in agent.report["dropped"]


def test_an_unusable_judge_reply_fails_closed(tmp_path: Path, base: Graph) -> None:
    rep = ReplayRespondent({}, default=UNKNOWN)
    agent = Elicitor(
        owner=OWNER,
        respondent=rep,
        session_id="f1",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    empty = ExchangeVerdicts(judgements=[])
    result = agent.run(state(base), ctx(tmp_path, provider(empty, met())))
    assert [q.subject_ref for q in rep.asked] == ["current_workaround"]
    assert any("could not be judged" in s for s in result.self_assessment.least_sure_about)  # type: ignore[attr-defined]


def test_a_claim_the_operator_already_made_at_t3_is_not_stated_twice(
    tmp_path: Path, base: Graph
) -> None:
    rep = ReplayRespondent(
        {"who_is_affected": observed("Finance leads at four clients")}, default=UNKNOWN
    )
    one = Elicitor(
        owner=OWNER,
        respondent=rep,
        session_id="d1",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    first = one.run(state(base), ctx(tmp_path, provider(met())))
    committed = FormulaValidator().settle(
        base.with_patch(first.proposed_nodes, first.proposed_edges)
    )
    rep2 = ReplayRespondent(
        {"who_is_affected": observed("Finance leads at four clients")}, default=UNKNOWN
    )
    two = Elicitor(
        owner=OWNER,
        respondent=rep2,
        session_id="d2",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    second = two.run(state(committed), ctx(tmp_path, provider(met())))
    assert two.report["duplicates"] == [0]
    assert not any(isinstance(n, Claim) for n in second.proposed_nodes)
    final = FormulaValidator().settle(
        committed.with_patch(second.proposed_nodes, second.proposed_edges)
    )
    c = next(c for c in claims(final) if c.text == "Finance leads at four clients")
    assert c.confidence.value == pytest.approx(
        0.30
    )  # one source, not corroborated by itself (OI46)


def test_the_agent_is_a_t3_producer(tmp_path: Path, base: Graph) -> None:
    agent = Elicitor(owner=OWNER, respondent=ReplayRespondent({}))
    assert agent.name == "elicitor" and agent.tier_policy.allowed == frozenset({Tier.T3})
    with pytest.raises(ValueError):
        agent.run(state(base), ctx(tmp_path, None))


def test_no_roster_or_mode_table_changed() -> None:
    from probative.graph_runtime.modes import ALL_CRITICS

    assert "bias_hunter" not in ALL_CRITICS  # D2: it runs inside the Elicitor
    assert Severity.BLOCK  # (kept so the import is exercised)


def test_a_turn_whose_question_fails_the_seal_audit_is_not_used_as_evidence(
    tmp_path: Path, base: Graph
) -> None:
    # a session file written elsewhere: its question was never judged here, so the seal audits it
    from probative.elicit.types import AskedQuestion, Option

    q = AskedQuestion(
        index=0,
        template_id="topic:who_is_affected",
        subject_ref="who_is_affected",
        text="Surely finance leads are frustrated, aren't they?",
        options=(
            Option(label="I will say what I know", kind=AnswerKind.OPEN),
            Option(label="I do not know", kind=AnswerKind.UNKNOWN),
        ),
        evidence_kind=None,
    )
    from probative.core.evidence import EvidenceKind

    q = q.model_copy(update={"evidence_kind": EvidenceKind.CUSTOMER})
    directory = tmp_path / "run1" / "elicitation" / "t1"
    Session(directory).append_round(
        0, [(q, observed("Finance leads at four clients"))], asked_at=NOW
    )
    agent = Elicitor(
        owner=OWNER,
        respondent=ReplayRespondent({}),
        session_id="t1",
        params=ElicitorInput(max_rounds=1),
    )
    result = agent.run(state(base), ctx(tmp_path, provider(leading())))
    assert agent.report["tainted"] == [0]
    assert not any(isinstance(n, Claim) for n in result.proposed_nodes)
    assert any(
        isinstance(n, Question) and "may have led it" in n.text for n in result.proposed_nodes
    )


# -- fixes from the independent review (PB14-p1) -------------------------------------------


def cannot_tell() -> ExchangeVerdicts:
    return ExchangeVerdicts(
        judgements=[CheckVerdict(check_id=c, verdict=Verdict.CANNOT_TELL) for c in JUDGED]
    )


def test_cannot_tell_on_a_blocking_check_fails_closed(tmp_path: Path, base: Graph) -> None:
    rep = ReplayRespondent({}, default=UNKNOWN)
    agent = Elicitor(
        owner=OWNER,
        respondent=rep,
        session_id="ct",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    agent.run(state(base), ctx(tmp_path, provider(cannot_tell(), met())))
    assert [q.subject_ref for q in rep.asked] == ["current_workaround"]
    assert "who_is_affected" in agent.report["dropped"]


def test_a_restated_claim_that_differs_only_in_whitespace_is_a_duplicate(
    tmp_path: Path, base: Graph
) -> None:
    one = Elicitor(
        owner=OWNER,
        respondent=ReplayRespondent({"who_is_affected": observed("Finance leads approve by hand")}),
        session_id="w1",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    first = one.run(state(base), ctx(tmp_path, provider(met())))
    committed = FormulaValidator().settle(
        base.with_patch(first.proposed_nodes, first.proposed_edges)
    )
    two = Elicitor(
        owner=OWNER,
        respondent=ReplayRespondent(
            {"who_is_affected": observed(" Finance leads  approve by hand ")}
        ),
        session_id="w2",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    second = two.run(state(committed), ctx(tmp_path, provider(met())))
    assert two.report["duplicates"] == [0]
    assert not any(isinstance(n, Claim) for n in second.proposed_nodes)


def test_the_same_answer_twice_in_one_session_is_one_claim(tmp_path: Path, base: Graph) -> None:
    same = observed("Finance leads approve by hand")
    agent = Elicitor(
        owner=OWNER,
        respondent=ReplayRespondent(
            {"who_is_affected": same, "current_workaround": same, "frequency": same}
        ),
        session_id="in1",
        params=ElicitorInput(round_size=3, max_rounds=1),
    )
    result = agent.run(state(base), ctx(tmp_path, provider(met(), met(), met())))
    assert len([n for n in result.proposed_nodes if isinstance(n, Claim)]) == 1
    assert len([n for n in result.proposed_nodes if isinstance(n, EvidenceSpan)]) == 1
    assert agent.report["duplicates"] == [1, 2]


def test_an_answer_the_question_did_not_offer_is_refused_before_it_is_saved(
    tmp_path: Path, base: Graph
) -> None:
    deny = RawAnswer(kind=AnswerKind.DENY)
    agent = Elicitor(
        owner=OWNER,
        respondent=ReplayRespondent({}, default=deny),
        session_id="bad",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    with pytest.raises(ValueError, match="not offered"):
        agent.run(state(base), ctx(tmp_path, provider(met())))
    assert Session(tmp_path / "run1" / "elicitation" / "bad").turns() == []  # nothing persisted
    # the session is not bricked: a good respondent can carry on
    ok = Elicitor(
        owner=OWNER,
        respondent=ReplayRespondent({}, default=UNKNOWN),
        session_id="bad",
        params=ElicitorInput(round_size=1, max_rounds=1),
    )
    ok.run(state(base), ctx(tmp_path, provider(met(), met())))


def test_two_runs_sharing_a_source_root_do_not_collide_on_the_default_session(
    tmp_path: Path, base: Graph
) -> None:
    def go(run: str) -> None:
        c = ctx(tmp_path, provider(met()))
        c = RunContext(
            provider=c.provider,
            model=c.model,
            run_dir=tmp_path / run,
            source_root=tmp_path,
            clock=c.clock,
            budget=c.budget,
            interactions=InteractionLog(tmp_path / run / "i.jsonl"),
        )
        Elicitor(
            owner=OWNER,
            respondent=ReplayRespondent({"who_is_affected": observed(f"Seen in {run}")}),
            params=ElicitorInput(round_size=1, max_rounds=1),
        ).run(state(base), c)

    go("runA")
    go("runB")  # no SealError
