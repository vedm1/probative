"""The phase machine (docs/DESIGN.md §9.1): LangGraph, an explicit state machine.

    produce -> validate -> fanout -> decide -+-> commit
       ^                                     +-> gate      (interrupt_before)
       +---------------- repair <------------+-> escalate  (interrupt_before)

* **produce** calls the phase's agent. It returns a patch; nothing is written.
* **validate** is `Committer.judge`: structure, I4 inputs, I1, I2, formulas.
* **fanout** runs the critics in parallel and joins their findings. It is skipped
  when a validator already failed (cheap before costly).
* **decide** sends a blocking patch back to the producer, at most three cycles
  (the repair loop is machine-side), then to a person as an *escalation*; a
  clean patch goes to a *gate* if the phase has one and the mode needs a person,
  else straight to **commit**.
* A gate or escalation pauses the run in `checkpoint.sqlite`. It can resume in
  another process, days later: the checkpoint holds ids and hashes only, and the
  patch, graph and findings are on disk.

A person only ever answers with a `GateDecision` (I6). `decide` is the one door.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Hashable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from probative.agents.contract import Agent
from probative.core.critic import Finding, Severity
from probative.core.graph.graph import Graph
from probative.core.graph.store import content_hash, read_graph
from probative.core.graph.validators import Violation
from probative.critics.base import Critic
from probative.graph_runtime.adapter import candidates_for
from probative.graph_runtime.budget import BudgetLedger
from probative.graph_runtime.committer import (
    CommitRejectedError,
    Committer,
    VarianceHook,
)
from probative.graph_runtime.fanout import CriticJob, run_critic_fanout
from probative.graph_runtime.gates import GateDecision, GateRejectReason, apply_amend
from probative.graph_runtime.modes import MODES, Mode
from probative.graph_runtime.patch import Patch, PatchStore
from probative.graph_runtime.phases import PHASES, Phase, PhaseSpec
from probative.graph_runtime.runfiles import RunFiles, append_jsonl
from probative.graph_runtime.state import GraphState, RunContext, RunState
from probative.graph_runtime.tedium import Interaction, InteractionLog, TediumAuditor
from probative.llm import Provider

MAX_REPAIR_CYCLES = 3
_RECURSION_LIMIT = 200

Status = Literal[
    "committed", "awaiting_gate", "awaiting_escalation", "budget_exhausted", "failed", "running"
]


class RunRefusedError(Exception):
    """The run cannot start, or cannot start this phase, as configured."""


class ModeViolationError(RunRefusedError):
    """A critic the mode omits was supplied (I9, OI22)."""


class StalePatchError(Exception):
    """A decision named a patch that is not the one now waiting for a person."""


class NoPendingDecisionError(Exception):
    """`decide` was called when nothing waits for a person."""


@dataclass(frozen=True)
class RunOutcome:
    status: Status
    phase: Phase
    patch_id: str | None
    cycle: int
    graph_hash: str | None


@dataclass(frozen=True)
class PendingDecision:
    kind: Literal["gate", "escalation"]
    phase: Phase
    gate: str | None
    patch: Patch
    findings: tuple[Finding, ...]
    violations: tuple[Violation, ...]
    cycle: int


class Runtime:
    def __init__(
        self,
        run_dir: Path,
        *,
        source_root: Path,
        mode: Mode,
        agents: Mapping[Phase, Agent],
        critics: Mapping[str, Critic],
        phases: Mapping[Phase, PhaseSpec] = PHASES,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        variance: VarianceHook | None = None,
        provider: Provider | None = None,
        model: str = "",
        workers: int = 8,
    ) -> None:
        self._mode = MODES[mode]
        omitted = sorted(set(critics) - self._mode.critics)
        if omitted:
            raise ModeViolationError(
                f"mode {mode.value} does not run {', '.join(omitted)}; it cannot be supplied"
            )
        self._files = RunFiles(run_dir)
        self._files.ensure()
        self._run_id = run_dir.name
        self._source_root = source_root
        self._agents = dict(agents)
        self._critics = dict(critics)
        self._phases = dict(phases)
        self._clock = clock
        self._monotonic = monotonic
        self._provider = provider
        self._model = model
        self._workers = workers
        self.committer = Committer(
            self._files, source_root=source_root, clock=clock, variance=variance
        )
        self.interactions = InteractionLog(self._files.interactions_path)
        self._patches = PatchStore(self._files)
        self._judged: tuple[tuple[str, str], Graph] | None = None
        self._conn = sqlite3.connect(self._files.checkpoint_path, check_same_thread=False)
        self._app = self._build().compile(
            checkpointer=SqliteSaver(self._conn), interrupt_before=["gate", "escalate"]
        )

    # -- public ----------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def start(self, phase: Phase, *, attempt: int = 1) -> RunOutcome:
        spec = self._phases[phase]
        if phase not in self._agents:
            raise RunRefusedError(f"no agent is registered for {phase.value}")
        missing = sorted(self._mode.effective_critics(spec) - set(self._critics))
        if missing:
            raise RunRefusedError(f"{phase.value} needs critics that were not supplied: {missing}")
        graph = self.committer.reconcile()
        dirty = self.committer.verify_clean(graph)
        if dirty:
            shown = ", ".join(f"{v.code} {v.node_id}" for v in dirty[:5])
            raise RunRefusedError(f"the graph already has {len(dirty)} violation(s): {shown}")
        cfg = self._config(phase, attempt)
        if self._app.get_state(cfg).values:
            raise RunRefusedError(f"{phase.value} attempt {attempt} already exists; use attempt+1")
        initial: RunState = {
            "run_id": self._run_id,
            "phase": phase.value,
            "mode": self._mode.mode.value,
            "cycle": 0,
            "findings": [],
            "violations": [],
            "gate_decision": None,
            "reject_reason": None,
            "pending_since": None,
            "spent_tokens": 0,
            "spent_seconds": 0.0,
            "status": "running",
            "graph_hash": content_hash(graph),
        }
        self._app.invoke(initial, cfg)
        return self._outcome(phase, attempt)

    def resume(self, phase: Phase, *, attempt: int = 1) -> RunOutcome:
        """Continue a run that stopped inside a step (an agent or critic raised, or
        the process died). It does not answer a gate: `decide` does that."""
        cfg = self._config(phase, attempt)
        snap = self._app.get_state(cfg)
        if not snap.next:
            raise RunRefusedError(f"{phase.value} attempt {attempt} has nothing to resume")
        self._guard(snap.values, hashed=True)
        self.committer.reconcile()
        if snap.next[0] in ("gate", "escalate"):
            raise RunRefusedError("this run waits for a person; use decide")
        self._app.invoke(None, cfg)
        return self._outcome(phase, attempt)

    def pending(self, phase: Phase, *, attempt: int = 1) -> PendingDecision | None:
        snap = self._app.get_state(self._config(phase, attempt))
        if snap.values:
            self._guard(snap.values, hashed=False)
        if not snap.next or snap.next[0] not in ("gate", "escalate"):
            return None
        values = snap.values
        spec = self._phases[phase]
        return PendingDecision(
            kind="gate" if snap.next[0] == "gate" else "escalation",
            phase=phase,
            gate=spec.gate.value
            if spec.gate and snap.next[0] == "gate" and self._mode.needs_human(spec.gate)
            else None,
            patch=self._patches.load(values["patch_id"]),
            findings=tuple(Finding.model_validate(d) for d in values.get("findings", [])),
            violations=tuple(Violation(**d) for d in values.get("violations", [])),
            cycle=int(values.get("cycle", 0)),
        )

    def decide(
        self, phase: Phase, decision: GateDecision, *, patch_id: str, attempt: int = 1
    ) -> RunOutcome:
        """Answer the pending gate or escalation. `patch_id` is the patch the person
        was shown; a decision about any other patch is refused, so a repeated or late
        answer cannot commit something nobody looked at."""
        pending = self.pending(phase, attempt=attempt)
        if pending is None:
            raise NoPendingDecisionError(f"nothing waits for a decision in {phase.value}")
        if patch_id != pending.patch.id:
            raise StalePatchError(f"waiting on {pending.patch.id}, not {patch_id}")
        cfg = self._config(phase, attempt)
        self._guard(self._app.get_state(cfg).values, hashed=True)
        if pending.kind == "escalation" and decision.kind == "accept":
            raise ValueError(
                "an escalation cannot be accepted: its patch is blocked; reject or amend it"
            )
        if decision.kind == "amend":
            apply_amend(pending.patch, decision.drop_ids)  # dry run: fail before recording
        since = self._app.get_state(cfg).values.get("pending_since")
        waited = (self._clock() - datetime.fromisoformat(since)).total_seconds() if since else 0.0
        self._app.update_state(cfg, {"gate_decision": decision.model_dump(mode="json")})
        self.interactions.record(
            Interaction(
                phase,
                pending.kind,
                max(0.0, waited),
                patch_id,
                decision.model_dump(mode="json"),
            )
        )
        self._app.invoke(None, cfg)
        return self._outcome(phase, attempt)

    def audit_tedium(self) -> list[Finding]:
        return TediumAuditor().audit(self.interactions.entries(), self._phases)

    # -- machine ---------------------------------------------------------------

    def _build(self) -> StateGraph:  # type: ignore[type-arg]
        g = StateGraph(RunState)
        g.add_node("produce", self._produce)
        g.add_node("validate", self._validate)
        g.add_node("fanout", self._fanout)
        g.add_node("decide", self._decide)
        g.add_node("gate", self._human)
        g.add_node("escalate", self._human)
        g.add_node("commit", self._commit)
        g.add_edge(START, "produce")
        g.add_conditional_edges(
            "produce",
            lambda s: "end" if s["status"] == "budget_exhausted" else "validate",
            {"end": END, "validate": "validate"},
        )
        g.add_edge("validate", "fanout")
        g.add_edge("fanout", "decide")
        routes: dict[Hashable, str] = {
            "produce": "produce",
            "gate": "gate",
            "escalate": "escalate",
            "commit": "commit",
        }
        g.add_conditional_edges("decide", lambda s: s["route"], routes)
        human: dict[Hashable, str] = {
            "commit": "commit",
            "produce": "produce",
            "validate": "validate",
        }
        g.add_conditional_edges("gate", lambda s: s["route"], human)
        g.add_conditional_edges("escalate", lambda s: s["route"], human)
        g.add_edge("commit", END)
        return g

    def _produce(self, state: RunState) -> dict[str, Any]:
        phase = Phase(state["phase"])
        ledger = self._ledger(state)
        if ledger.view().exhausted:
            return {"status": "budget_exhausted"}
        cycle = state["cycle"] + 1
        reason = state.get("reject_reason")
        graph_state = GraphState(
            graph=self._graph(),
            phase=phase,
            mode=self._mode.mode,
            cycle=cycle,
            prior_findings=tuple(Finding.model_validate(d) for d in state["findings"]),
            prior_violations=tuple(Violation(**d) for d in state["violations"]),
            reject_reason=GateRejectReason(reason) if reason else None,
        )
        ctx = RunContext(
            provider=self._provider,
            model=self._model,
            run_dir=self._files.root,
            source_root=self._source_root,
            clock=self._clock,
            budget=ledger.view(),
            interactions=self.interactions,
        )
        agent = self._agents[phase]
        began = self._monotonic()
        result = agent.run(graph_state, ctx)
        ledger.charge(tokens=result.cost.total_tokens, seconds=self._monotonic() - began)
        patch = Patch.build(agent.name, phase, cycle, result)
        self._patches.save(patch)
        append_jsonl(
            self._files.assumptions_path,
            {
                "patch_id": patch.id,
                "agent": agent.name,
                "least_sure_about": list(result.self_assessment.least_sure_about),
            },
        )
        return {
            "cycle": cycle,
            "patch_id": patch.id,
            "reject_reason": None,
            "status": "running",
            **self._spent(ledger),
        }

    def _validate(self, state: RunState) -> dict[str, Any]:
        patch = self._patches.load(state["patch_id"])
        judged = self.committer.judge(
            self._graph(), patch, policy=self._agents[patch.phase].tier_policy
        )
        if judged.graph_after is not None:
            self._judged = ((patch.id, state["graph_hash"]), judged.graph_after)
        return {"violations": [asdict(v) for v in judged.violations]}

    def _fanout(self, state: RunState) -> dict[str, Any]:
        if state["violations"]:
            return {"findings": []}
        phase = Phase(state["phase"])
        wanted = sorted(self._mode.effective_critics(self._phases[phase]))
        if not wanted:
            return {"findings": []}
        ledger = self._ledger(state)
        if ledger.view().exhausted:
            skipped = [
                Finding(
                    critic_id=critic_id,
                    check_id="critic_skipped_budget",
                    severity=Severity.WARN,
                    invariant=None,
                    message=f"{critic_id} did not run: the {phase.value} budget was spent",
                    remedy="Raise the phase budget, or review this patch without that critic.",
                )
                for critic_id in wanted
            ]
            return {"findings": [f.model_dump(mode="json") for f in skipped]}
        patch = self._patches.load(state["patch_id"])
        after = self._after(patch, state)
        ids = [n.id for n in patch.result.proposed_nodes]
        jobs: list[CriticJob] = []
        node_of: dict[str, str] = {}
        for critic_id in wanted:
            found = candidates_for(after, ids, with_traced_stories=critic_id == "constraint_critic")
            node_of.update(found.node_of)
            jobs.append((critic_id, self._critics[critic_id], found.candidates))
        began = self._monotonic()
        out = run_critic_fanout(jobs, workers=self._workers)
        ledger.charge(tokens=out.tokens, seconds=self._monotonic() - began)
        findings = [
            f.model_copy(update={"target_id": node_of.get(f.target_id, f.target_id)})
            if f.target_id
            else f
            for f in out.findings
        ]
        return {"findings": [f.model_dump(mode="json") for f in findings], **self._spent(ledger)}

    def _decide(self, state: RunState) -> dict[str, Any]:
        phase = Phase(state["phase"])
        spec = self._phases[phase]
        findings = [Finding.model_validate(d) for d in state["findings"]]
        blocking = bool(state["violations"]) or any(f.severity is Severity.BLOCK for f in findings)
        patch = self._patches.load(state["patch_id"])
        now = self._clock().isoformat()
        if blocking:
            self._patches.save_rejected(
                patch, findings, [Violation(**d) for d in state["violations"]]
            )
            route = "produce" if state["cycle"] < MAX_REPAIR_CYCLES else "escalate"
            return {
                "blocking": True,
                "route": route,
                "pending_since": now if route == "escalate" else None,
                "status": "awaiting_escalation" if route == "escalate" else "running",
            }
        unreviewed = any(f.check_id == "critic_skipped_budget" for f in findings)
        if self._mode.needs_human(spec.gate) or unreviewed:
            # A patch whose critics did not run is never committed unseen, gate or not.
            return {
                "blocking": False,
                "route": "gate",
                "pending_since": now,
                "status": "awaiting_gate",
            }
        return {"blocking": False, "route": "commit", "pending_since": None}

    def _human(self, state: RunState) -> dict[str, Any]:
        raw = state.get("gate_decision")
        if raw is None:
            raise NoPendingDecisionError("resumed without a decision")
        decision = GateDecision.model_validate(raw)
        cleared: dict[str, Any] = {"gate_decision": None, "pending_since": None}
        if decision.kind == "accept":
            return {**cleared, "route": "commit", "status": "running"}
        if decision.kind == "reject":
            assert decision.reason is not None
            return {
                **cleared,
                "route": "produce",
                "cycle": 0,
                "reject_reason": decision.reason.value,
                "status": "running",
            }
        amended = apply_amend(self._patches.load(state["patch_id"]), decision.drop_ids)
        self._patches.save(amended)
        return {**cleared, "route": "validate", "patch_id": amended.id, "status": "running"}

    def _commit(self, state: RunState) -> dict[str, Any]:
        patch = self._patches.load(state["patch_id"])
        findings = [Finding.model_validate(d) for d in state["findings"]]
        try:
            result = self.committer.commit(
                self._graph(), patch, findings, policy=self._agents[patch.phase].tier_policy
            )
        except CommitRejectedError as err:
            self._patches.save_rejected(patch, findings, err.violations)
            return {"status": "failed", "violations": [asdict(v) for v in err.violations]}
        return {"status": "committed", "graph_hash": result.content_hash}

    # -- helpers ---------------------------------------------------------------

    def _guard(self, values: Mapping[str, Any], *, hashed: bool) -> None:
        """A run belongs to the mode it started in, and to the graph it started from."""
        if values.get("mode") != self._mode.mode.value:
            raise ModeViolationError(
                f"this run started in {values.get('mode')} mode, not {self._mode.mode.value}"
            )
        if hashed:
            now = content_hash(self._graph())
            if values.get("graph_hash") != now:
                raise RunRefusedError(
                    f"graph.json changed while this run waited: it was {values.get('graph_hash')}, "
                    f"it is {now}"
                )

    def _config(self, phase: Phase, attempt: int) -> Any:
        return {
            "configurable": {"thread_id": f"{self._run_id}:{phase.value}:{attempt}"},
            "recursion_limit": _RECURSION_LIMIT,
        }

    def _graph(self) -> Graph:
        path = self._files.graph_path
        return read_graph(path) if path.is_file() else Graph.empty()

    def _after(self, patch: Patch, state: RunState) -> Graph:
        key = (patch.id, state["graph_hash"])
        if self._judged is not None and self._judged[0] == key:
            return self._judged[1]
        judged = self.committer.judge(
            self._graph(), patch, policy=self._agents[patch.phase].tier_policy
        )
        assert judged.graph_after is not None
        return judged.graph_after

    def _ledger(self, state: RunState) -> BudgetLedger:
        spec = self._phases[Phase(state["phase"])]
        return BudgetLedger(
            token_budget=spec.token_budget,
            wall_seconds=spec.wall_seconds,
            spent_tokens=state["spent_tokens"],
            spent_seconds=state["spent_seconds"],
        )

    @staticmethod
    def _spent(ledger: BudgetLedger) -> dict[str, Any]:
        return {"spent_tokens": ledger.spent_tokens, "spent_seconds": ledger.spent_seconds}

    def _outcome(self, phase: Phase, attempt: int) -> RunOutcome:
        snap = self._app.get_state(self._config(phase, attempt))
        values = snap.values
        status: Status = values.get("status", "running")
        if snap.next:
            status = "awaiting_gate" if snap.next[0] == "gate" else "awaiting_escalation"
        return RunOutcome(
            status=status,
            phase=phase,
            patch_id=values.get("patch_id"),
            cycle=int(values.get("cycle", 0)),
            graph_hash=values.get("graph_hash"),
        )
