"""The Committer: the only thing that turns a patch into graph state."""

from __future__ import annotations

from pathlib import Path

import pytest

import probative.formulas  # noqa: F401  (registers the Olsen formulas)
from probative.agents.contract import TierPolicy
from probative.core.critic import Finding, Severity
from probative.core.evidence import Tier
from probative.core.graph import store
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.mirror import load_mirror
from probative.core.graph.nodes import Claim, Need, Opportunity
from probative.core.graph.values import Computed
from probative.formulas.validator import FormulaValidator
from probative.graph_runtime import committer as committer_module
from probative.graph_runtime.committer import CommitRejectedError, Committer
from probative.graph_runtime.patch import Patch
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.runfiles import RunFiles, read_jsonl
from tests.core.graph._samples import ENV, conf
from tests.graph_runtime._support import (
    ALL_TIERS,
    NOW,
    clock,
    good_ratings,
    hypothesis_with_test,
    opportunity,
    result,
)


def make(tmp_path: Path, **kw: object) -> tuple[Committer, RunFiles]:
    files = RunFiles(tmp_path / "run")
    files.ensure()
    return Committer(files, source_root=tmp_path, clock=clock, **kw), files  # type: ignore[arg-type]


def patch_of(nodes, edges=None, *, cycle: int = 1) -> Patch:  # type: ignore[no-untyped-def]
    return Patch.build("scripted", Phase.P3, cycle, result(nodes, edges))


def codes(err: CommitRejectedError) -> set[str]:
    return {v.code for v in err.violations}


def rating_patch() -> tuple[Patch, list]:  # type: ignore[type-arg]
    imp, sat = good_ratings()
    opp = opportunity([imp, sat], value=None)
    return patch_of([imp, sat, opp]), [imp, sat, opp]


# -- the happy path ---------------------------------------------------------


def test_a_clean_patch_commits_and_the_formula_fills_the_number(tmp_path: Path) -> None:
    c, files = make(tmp_path)
    patch, (_imp, _sat, opp) = rating_patch()
    out = c.commit(Graph.empty(), patch, [], policy=ALL_TIERS)
    stored = out.graph.nodes[opp.id]
    assert isinstance(stored, Opportunity)
    assert stored.value.value == 15  # Olsen p. 57: importance 10, satisfaction 5 gives 15
    assert stored.id == opp.id  # recomputing a Computed does not re-id the node
    assert store.content_hash(store.read_graph(files.graph_path)) == out.content_hash
    assert FormulaValidator().check(out.graph) == []
    load_mirror(files.mirror_path, expected=out.graph)


def test_the_ledger_records_the_commit(tmp_path: Path) -> None:
    c, files = make(tmp_path)
    patch, _ = rating_patch()
    out = c.commit(Graph.empty(), patch, [], policy=ALL_TIERS)
    (line,) = read_jsonl(files.ledger_path)
    assert line["patch_id"] == patch.id and line["after_hash"] == out.content_hash
    assert line["before_hash"] == store.content_hash(Graph.empty())
    assert line["kind"] == "commit" and line["phase"] == "P3"


def test_a_second_commit_is_judged_against_the_whole_graph(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    patch, _ = rating_patch()
    first = c.commit(Graph.empty(), patch, [], policy=ALL_TIERS)
    need = Need.make(text="Reduce the time I spend re-keying data", **ENV)
    second = c.commit(first.graph, patch_of([need]), [], policy=ALL_TIERS)
    assert need.id in second.graph.nodes and len(second.graph.nodes) == 4


# -- rejections: each its own code ------------------------------------------


def reject(c: Committer, patch: Patch, graph: Graph | None = None) -> CommitRejectedError:
    with pytest.raises(CommitRejectedError) as info:
        c.commit(graph or Graph.empty(), patch, [], policy=ALL_TIERS)
    return info.value


def test_a_dangling_edge_is_a_structure_rejection_not_a_crash(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    need = Need.make(text="Reduce the time I spend re-keying data", **ENV)
    edge = Edge.make(
        type=EdgeType.LADDERS_UP_TO, src=need.id, dst="need_" + "f" * 12, owner="v", asserted_at=NOW
    )
    assert codes(reject(c, patch_of([need], [edge]))) == {"STRUCTURE"}


def test_an_agent_supplied_number_is_rejected_even_when_it_is_right(tmp_path: Path) -> None:
    c, files = make(tmp_path)
    imp, sat = good_ratings()
    for value in (99.0, 15.0):
        err = reject(c, patch_of([imp, sat, opportunity([imp, sat], value=value)]))
        assert "I4_AGENT_VALUE" in codes(err)
    assert not files.graph_path.exists()


def test_an_orphan_claim_is_rejected_i1(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    claim = Claim.make(
        text="Users wait.",
        tier=Tier.T1,
        confidence=Computed(value=None, formula_id="claim_confidence", input_ids=[]),
        **ENV,
    )
    found = codes(reject(c, patch_of([claim])))
    assert "I1_ORPHAN_CLAIM" in found
    assert "I4_UNKNOWN_FORMULA" in found  # OI34: no formula until PB13, and no allow-list


def test_a_claim_cannot_be_slipped_past_with_a_made_up_value(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    claim = Claim.make(text="Users wait.", tier=Tier.T3, confidence=conf(), **ENV)
    assert "I4_AGENT_VALUE" in codes(reject(c, patch_of([claim])))


def test_a_hypothesis_without_a_test_is_rejected_i2(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    nodes, _edges = hypothesis_with_test()
    assert "I2_NO_TEST" in codes(reject(c, patch_of([nodes[0]])))


def test_a_hypothesis_with_its_test_commits(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    nodes, edges = hypothesis_with_test()
    out = c.commit(Graph.empty(), patch_of(nodes, edges), [], policy=ALL_TIERS)
    assert {n.id for n in nodes} <= set(out.graph.nodes)


def test_an_unknown_formula_is_rejected(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    imp, sat = good_ratings()
    bad = Opportunity.make(
        value=Computed(value=None, formula_id="made_up", input_ids=[imp.id, sat.id]), **ENV
    )
    assert "I4_UNKNOWN_FORMULA" in codes(reject(c, patch_of([imp, sat, bad])))


def test_a_tier_outside_the_agents_policy_is_rejected(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    patch, _ = rating_patch()  # ratings are tier T1
    policy = TierPolicy(allowed=frozenset({Tier.T3}))
    with pytest.raises(CommitRejectedError) as info:
        c.commit(Graph.empty(), patch, [], policy=policy)
    assert "TIER_POLICY" in codes(info.value)


# -- OI36b: both validators run, together -----------------------------------


def hypothesis_only() -> Patch:
    nodes, _ = hypothesis_with_test()
    return patch_of([nodes[0]])


def unknown_formula_only() -> Patch:
    imp, sat = good_ratings()
    bad = Opportunity.make(
        value=Computed(value=None, formula_id="made_up", input_ids=[imp.id, sat.id]), **ENV
    )
    return patch_of([imp, sat, bad])


def test_removing_validate_graph_lets_an_i2_defect_through_so_the_test_is_sensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(committer_module, "validate_graph", lambda *a, **k: [])
    c, _ = make(tmp_path)
    c.commit(Graph.empty(), hypothesis_only(), [], policy=ALL_TIERS)  # would raise if wired


def test_removing_the_formula_validator_lets_an_unknown_formula_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Blind:
        def __init__(self, *a: object, **k: object) -> None: ...
        def check(self, graph: Graph) -> list:  # type: ignore[type-arg]
            return []

        def recompute(self, graph: Graph) -> dict:  # type: ignore[type-arg]
            return {}

    monkeypatch.setattr(committer_module, "FormulaValidator", Blind)
    c, _ = make(tmp_path)
    c.commit(Graph.empty(), unknown_formula_only(), [], policy=ALL_TIERS)


def test_both_validators_report_together_not_one_after_the_other(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    nodes, _ = hypothesis_with_test()
    imp, sat = good_ratings()
    bad = Opportunity.make(
        value=Computed(value=None, formula_id="made_up", input_ids=[imp.id, sat.id]), **ENV
    )
    found = codes(reject(c, patch_of([nodes[0], imp, sat, bad])))
    assert {"I2_NO_TEST", "I4_UNKNOWN_FORMULA"} <= found


# -- atomicity and recovery -------------------------------------------------


def test_a_rejected_patch_changes_nothing_on_disk(tmp_path: Path) -> None:
    c, files = make(tmp_path)
    patch, _ = rating_patch()
    first = c.commit(Graph.empty(), patch, [], policy=ALL_TIERS)
    before = files.graph_path.read_bytes()
    nodes, _ = hypothesis_with_test()
    reject(c, patch_of([nodes[0]]), first.graph)
    assert files.graph_path.read_bytes() == before
    assert len(read_jsonl(files.ledger_path)) == 1


def test_a_crash_between_graph_write_and_ledger_is_repaired_by_reconcile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, files = make(tmp_path)
    patch, _ = rating_patch()

    def boom(*a: object, **k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(committer_module, "append_jsonl", boom)
    with pytest.raises(OSError):
        c.commit(Graph.empty(), patch, [], policy=ALL_TIERS)
    assert files.graph_path.exists() and read_jsonl(files.ledger_path) == []
    monkeypatch.undo()
    graph = c.reconcile()
    (line,) = read_jsonl(files.ledger_path)
    assert line["kind"] == "recovered"
    assert line["after_hash"] == store.content_hash(graph)
    c.reconcile()
    assert len(read_jsonl(files.ledger_path)) == 1  # idempotent


def test_reconcile_on_an_empty_run_does_nothing(tmp_path: Path) -> None:
    c, files = make(tmp_path)
    assert c.reconcile().nodes == {}
    assert read_jsonl(files.ledger_path) == []


# -- findings become nodes --------------------------------------------------


def test_surviving_findings_become_finding_nodes_with_a_flagged_by_edge(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    need = Need.make(text="Reduce the time I spend re-keying data", **ENV)
    warn = Finding(
        critic_id="space_warden", check_id="bad", severity=Severity.WARN, invariant="I3",
        message="check wording", remedy="restate", target_id=need.id,
    )  # fmt: skip
    note = Finding(
        critic_id="x", check_id="n", severity=Severity.NOTE, invariant=None,
        message="fyi", remedy="none", target_id=None,
    )  # fmt: skip
    out = c.commit(Graph.empty(), patch_of([need]), [warn, note], policy=ALL_TIERS)
    flagged = out.graph.out_edges(need.id, EdgeType.FLAGGED_BY)
    assert len(flagged) == 1
    node = out.graph.nodes[flagged[0].dst]
    assert node.type_name() == "finding" and node.owner == "critic:space_warden"  # type: ignore[attr-defined]
    assert len(out.finding_nodes) == 1  # the target-less note stays in the ledger only


def test_a_blocking_finding_cannot_be_committed_over(tmp_path: Path) -> None:
    c, files = make(tmp_path)
    need = Need.make(text="Reduce the time I spend re-keying data", **ENV)
    block = Finding(
        critic_id="space_warden", check_id="bad", severity=Severity.BLOCK, invariant="I3",
        message="m", remedy="r", target_id=need.id,
    )  # fmt: skip
    with pytest.raises(CommitRejectedError) as info:
        c.commit(Graph.empty(), patch_of([need]), [block], policy=ALL_TIERS)
    assert "BLOCKING_FINDING" in codes(info.value)
    assert not files.graph_path.exists()


# -- I7: variance runs synchronously, before the write ----------------------


class SpyVariance:
    def __init__(self, files: RunFiles, *, raises: bool = False) -> None:
        self.files, self.raises = files, raises
        self.calls: list[tuple[int, bool]] = []

    def on_commit(self, before: Graph, after: Graph, patch: Patch) -> None:
        self.calls.append((len(after.nodes), self.files.graph_path.exists()))
        if self.raises:
            raise RuntimeError("variance exceeds baseline")


def test_the_variance_hook_runs_once_before_the_graph_is_written(tmp_path: Path) -> None:
    files = RunFiles(tmp_path / "run")
    files.ensure()
    spy = SpyVariance(files)
    c = Committer(files, source_root=tmp_path, clock=clock, variance=spy)
    patch, _ = rating_patch()
    c.commit(Graph.empty(), patch, [], policy=ALL_TIERS)
    assert spy.calls == [(3, False)]


def test_a_variance_failure_leaves_the_graph_untouched(tmp_path: Path) -> None:
    files = RunFiles(tmp_path / "run")
    files.ensure()
    c = Committer(
        files, source_root=tmp_path, clock=clock, variance=SpyVariance(files, raises=True)
    )
    patch, _ = rating_patch()
    with pytest.raises(CommitRejectedError) as info:
        c.commit(Graph.empty(), patch, [], policy=ALL_TIERS)
    assert "VARIANCE" in codes(info.value)
    assert not files.graph_path.exists() and read_jsonl(files.ledger_path) == []


# -- starting from a graph that is not clean --------------------------------


def test_verify_clean_reports_a_graph_that_already_has_violations(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    claim = Claim.make(text="Users wait.", tier=Tier.T3, confidence=conf(), **ENV)
    dirty = Graph.empty().with_patch(nodes=[claim])
    assert {v.code for v in c.verify_clean(dirty)} >= {"I1_ORPHAN_CLAIM"}
    assert c.verify_clean(Graph.empty()) == []
