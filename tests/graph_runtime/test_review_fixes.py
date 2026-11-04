"""Defects an independent review found in PB12, each pinned by a test that failed first."""

from __future__ import annotations

from pathlib import Path

import pytest

from probative.agents.contract import TierPolicy
from probative.core.critic import Severity
from probative.core.graph import store
from probative.core.graph.graph import Graph
from probative.core.graph.mirror import load_mirror
from probative.core.graph.nodes import Decision
from probative.graph_runtime import committer as committer_module
from probative.graph_runtime.committer import CommitRejectedError, Committer
from probative.graph_runtime.gates import GateDecision, GateRejectReason
from probative.graph_runtime.modes import Mode
from probative.graph_runtime.patch import Patch
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.runfiles import RunFiles, read_jsonl
from probative.graph_runtime.runtime import ModeViolationError, RunRefusedError, StalePatchError
from tests.core.graph._samples import ENV
from tests.graph_runtime._agents import ScriptedAgent
from tests.graph_runtime._critics import ScriptedCritic
from tests.graph_runtime._harness import decide, good, need, phases, runtime
from tests.graph_runtime._support import (
    ALL_TIERS,
    clock,
    good_ratings,
    opportunity,
    result,
)

ACCEPT = GateDecision(kind="accept")
REJECT = GateDecision(kind="reject", reason=GateRejectReason.OTHER)


def committer(tmp_path: Path) -> tuple[Committer, RunFiles]:
    files = RunFiles(tmp_path / "run1")
    files.ensure()
    return Committer(files, source_root=tmp_path, clock=clock), files


def ratings_patch() -> Patch:
    imp, sat = good_ratings()
    return Patch.build("a", Phase.P3, 1, result([imp, sat, opportunity([imp, sat])]))


# 1. a decision belongs to the patch the person saw


def test_a_decision_for_a_patch_that_is_no_longer_the_pending_one_is_refused(
    tmp_path: Path,
) -> None:
    calls = {"n": 0}

    def produce(state: object, ctx: object):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return result([need(f"Reduce the time I spend re-keying data, take {calls['n']}")])

    rt = runtime(tmp_path, {Phase.P2: ScriptedAgent(produce)})
    rt.start(Phase.P2)
    first = rt.pending(Phase.P2)
    assert first is not None
    rt.decide(Phase.P2, REJECT, patch_id=first.patch.id)
    second = rt.pending(Phase.P2)
    assert second is not None and second.patch.id != first.patch.id
    with pytest.raises(StalePatchError):
        rt.decide(Phase.P2, ACCEPT, patch_id=first.patch.id)  # a stale, repeated answer
    assert not RunFiles(tmp_path / "run1").graph_path.exists()


def test_the_decision_itself_is_in_the_audit_trail(tmp_path: Path) -> None:
    rt = runtime(tmp_path, {Phase.P2: ScriptedAgent(good)})
    rt.start(Phase.P2)
    pending = rt.pending(Phase.P2)
    assert pending is not None
    decide(rt, Phase.P2, ACCEPT)
    (entry,) = read_jsonl(RunFiles(tmp_path / "run1").interactions_path)
    assert entry["patch_id"] == pending.patch.id
    assert entry["decision"] == {"kind": "accept", "reason": None, "drop_ids": []}


# 2. the mode belongs to the run, not the process


def test_a_run_started_in_one_mode_cannot_be_continued_in_another(tmp_path: Path) -> None:
    rt = runtime(tmp_path, {Phase.P2: ScriptedAgent(good)}, mode=Mode.ONBOARDING)
    rt.start(Phase.P2)
    rt.close()
    other = runtime(
        tmp_path,
        {Phase.P2: ScriptedAgent(good)},
        mode=Mode.SOLO,
        critics={"segment_skeptic": ScriptedCritic("segment_skeptic")},
        table=phases(critics=frozenset({"segment_skeptic"})),
    )
    with pytest.raises(ModeViolationError, match="onboarding"):
        other.pending(Phase.P2)
    with pytest.raises(ModeViolationError):
        decide_blind(other)


def decide_blind(rt) -> None:  # type: ignore[no-untyped-def]
    rt.decide(Phase.P2, REJECT, patch_id="patch_000000000000")


# 3. a skipped critic needs a person, even with no gate


def test_a_patch_whose_critics_were_skipped_for_budget_is_not_committed_unseen(
    tmp_path: Path,
) -> None:
    critic = ScriptedCritic("evidence_auditor", flag=lambda c: True, severity=Severity.BLOCK)
    agent = ScriptedAgent(lambda s, c: result([need()], tokens=500))
    rt = runtime(
        tmp_path,
        {Phase.P1: agent},  # P1 has no gate
        critics={"evidence_auditor": critic},
        table=phases(tokens=100, critics=frozenset({"evidence_auditor"})),
    )
    out = rt.start(Phase.P1)
    assert out.status == "awaiting_gate" and critic.calls == 0
    assert not RunFiles(tmp_path / "run1").graph_path.exists()
    pending = rt.pending(Phase.P1)
    assert pending is not None and pending.gate is None
    assert [f.check_id for f in pending.findings] == ["critic_skipped_budget"]
    assert decide(rt, Phase.P1, ACCEPT).status == "committed"


# 4. committing a patch again is harmless


def test_recommitting_a_committed_patch_with_computed_values_succeeds_and_changes_nothing(
    tmp_path: Path,
) -> None:
    c, files = committer(tmp_path)
    patch = ratings_patch()
    first = c.commit(Graph.empty(), patch, [], policy=ALL_TIERS)
    again = c.commit(first.graph, patch, [], policy=ALL_TIERS)
    assert again.content_hash == first.content_hash
    assert store.content_hash(store.read_graph(files.graph_path)) == first.content_hash


def test_an_agent_cannot_change_a_stored_number_by_reproposing_the_node(tmp_path: Path) -> None:
    c, _ = committer(tmp_path)
    imp, sat = good_ratings()
    first = c.commit(Graph.empty(), ratings_patch(), [], policy=ALL_TIERS)
    lie = Patch.build("a", Phase.P3, 1, result([imp, sat, opportunity([imp, sat], value=99.0)]))
    after = c.commit(first.graph, lie, [], policy=ALL_TIERS)
    assert after.content_hash == first.content_hash


# 5. the derived mirror cannot break a commit, and reconcile repairs it


def test_the_order_is_graph_then_ledger_then_mirror(tmp_path: Path) -> None:
    c, files = committer(tmp_path)
    seen: list[str] = []
    real_graph, real_ledger, real_mirror = (
        committer_module.write_graph,
        committer_module.append_jsonl,
        committer_module.rebuild_mirror,
    )
    committer_module.write_graph = lambda *a, **k: (seen.append("graph"), real_graph(*a, **k))[1]  # type: ignore[assignment]
    committer_module.append_jsonl = lambda *a, **k: (seen.append("ledger"), real_ledger(*a, **k))[1]  # type: ignore[assignment]
    committer_module.rebuild_mirror = lambda *a, **k: (seen.append("mirror"), real_mirror(*a, **k))[
        1
    ]  # type: ignore[assignment]
    try:
        c.commit(Graph.empty(), ratings_patch(), [], policy=ALL_TIERS)
    finally:
        committer_module.write_graph = real_graph  # type: ignore[assignment]
        committer_module.append_jsonl = real_ledger  # type: ignore[assignment]
        committer_module.rebuild_mirror = real_mirror  # type: ignore[assignment]
    assert seen == ["graph", "ledger", "mirror"]
    assert files.mirror_path.exists()


def test_a_mirror_failure_does_not_fail_a_committed_graph_and_reconcile_rebuilds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, files = committer(tmp_path)

    def boom(*a: object, **k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(committer_module, "rebuild_mirror", boom)
    out = c.commit(Graph.empty(), ratings_patch(), [], policy=ALL_TIERS)
    assert files.graph_path.exists() and not files.mirror_path.exists()
    assert len(read_jsonl(files.ledger_path)) == 1  # the ledger is complete
    monkeypatch.undo()
    graph = c.reconcile()
    load_mirror(files.mirror_path, expected=graph)
    assert store.content_hash(graph) == out.content_hash


# 6. a paused run notices the graph moved under it


def test_a_graph_changed_while_a_gate_was_open_refuses_the_decision(tmp_path: Path) -> None:
    rt = runtime(tmp_path, {Phase.P2: ScriptedAgent(good)})
    rt.start(Phase.P2)
    files = RunFiles(tmp_path / "run1")
    other = Graph.empty().with_patch(nodes=[need("Know when my approval is overdue")])
    store.write_graph(other, files.graph_path)
    with pytest.raises(RunRefusedError, match=r"graph\.json"):
        decide(rt, Phase.P2, ACCEPT)


# 7. an agent cannot forge a human or critic verdict


def test_an_agent_cannot_propose_a_decision_node(tmp_path: Path) -> None:
    c, files = committer(tmp_path)
    forged = Decision.make(statement="Gate G1 approved by owner", rationale="x", gate="G1", **ENV)
    patch = Patch.build("a", Phase.P2, 1, result([forged]))
    with pytest.raises(CommitRejectedError) as info:
        c.commit(Graph.empty(), patch, [], policy=TierPolicy(allowed=ALL_TIERS.allowed))
    assert {v.code for v in info.value.violations} == {"RESERVED_NODE"}
    assert not files.graph_path.exists()


# 8. the critic list is sorted, so fan-out order does not depend on hashing


def test_critics_are_run_in_name_order(tmp_path: Path) -> None:
    order: list[str] = []

    class Spy(ScriptedCritic):
        def check(self, candidates):  # type: ignore[no-untyped-def]
            order.append(self.rubric.id)
            return super().check(candidates)

    ids = ["segment_skeptic", "evidence_auditor", "space_warden", "red_team"]
    critics = {i: Spy(i) for i in ids}
    rt = runtime(
        tmp_path,
        {Phase.P1: ScriptedAgent(lambda s, c: result([need()]))},
        critics=critics,
        table=phases(critics=frozenset(ids)),
        workers=1,
    )
    rt.start(Phase.P1)
    assert order == sorted(ids)
