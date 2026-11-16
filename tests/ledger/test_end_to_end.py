"""PB13 gating check: the synthetic corpus runs through the P0 `Runtime` to a graph
that is clean under both validators, with the numbers filled by the formula. Every
number here is about synthetic data (OI4 is open)."""

from __future__ import annotations

from pathlib import Path

import pytest

import probative.formulas  # noqa: F401  (registers the formulas)
from probative.core.graph import store
from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, Question
from probative.core.graph.validators import validate_graph
from probative.formulas.validator import FormulaValidator
from probative.graph_runtime.modes import Mode
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.runfiles import RunFiles
from probative.graph_runtime.runtime import Runtime
from probative.ledger.agent import EvidenceLedger
from probative.ledger.contradict import PairJudgement, PairVerdict
from probative.llm import FakeProvider, TokenUsage
from tests.graph_runtime._harness import phases
from tests.graph_runtime._support import clock
from tests.ledger import _corpus

USAGE = TokenUsage(input_tokens=100, output_tokens=5)


def runtime(
    root: Path, *, mode: Mode = Mode.SOLO, judge: PairVerdict = PairVerdict.CONTRADICTS
) -> Runtime:
    provider = FakeProvider(
        [*_corpus.extraction_script(), PairJudgement(verdict=judge)], usage=USAGE
    )
    return Runtime(
        root / "run1",
        source_root=root,
        mode=mode,
        agents={Phase.P0: EvidenceLedger(owner="ved")},
        critics={},
        phases=phases(critics=frozenset()),
        clock=clock,
        provider=provider,
        model="test-model",
    )


def final_graph(root: Path) -> Graph:
    return store.read_graph(RunFiles(root / "run1").graph_path)


def claim_named(g: Graph, text: str) -> Claim:
    (c,) = [n for n in g.nodes.values() if isinstance(n, Claim) and n.text == text]
    return c


def test_the_corpus_commits_clean_with_the_formula_filling_every_number(tmp_path: Path) -> None:
    _corpus.build(tmp_path)
    rt = runtime(tmp_path)
    out = rt.start(Phase.P0)
    assert out.status == "committed"
    g = final_graph(tmp_path)
    assert validate_graph(g, source_root=tmp_path) == []
    assert FormulaValidator().check(g) == []
    assert claim_named(g, _corpus.APPROVALS_SLOW).confidence.value == pytest.approx(0.75)  # a and b
    assert claim_named(g, _corpus.APPROVALS_FAST).confidence.value == pytest.approx(0.5)
    assert claim_named(g, _corpus.SECOND).confidence.value == pytest.approx(0.5)
    rt.close()


def test_the_contradiction_is_preserved_not_averaged(tmp_path: Path) -> None:
    _corpus.build(tmp_path)
    runtime(tmp_path).start(Phase.P0)
    g = final_graph(tmp_path)
    slow, fast = claim_named(g, _corpus.APPROVALS_SLOW), claim_named(g, _corpus.APPROVALS_FAST)
    first, second = sorted((slow, fast), key=lambda c: c.id)
    assert [e.dst for e in g.out_edges(first.id, EdgeType.CONTRADICTS)] == [second.id]
    (q,) = [
        n for n in g.nodes.values() if isinstance(n, Question) and n.raised_by == "contradiction"
    ]
    assert {e.dst for e in g.out_edges(q.id, EdgeType.RAISED_ABOUT)} == {slow.id, fast.id}
    assert slow.confidence.value == pytest.approx(0.75)  # a disagreement changes no confidence


def test_the_run_is_deterministic_across_separate_directories(tmp_path: Path) -> None:
    hashes = []
    for name in ("one", "two"):
        root = tmp_path / name
        root.mkdir()
        _corpus.build(root)
        rt = runtime(root)
        rt.start(Phase.P0)
        rt.close()
        hashes.append(store.content_hash(final_graph(root)))
    assert hashes[0] == hashes[1]


def test_a_second_run_over_a_committed_graph_adds_nothing(tmp_path: Path) -> None:
    _corpus.build(tmp_path)
    first = runtime(tmp_path)
    first.start(Phase.P0)
    first.close()
    before = store.content_hash(final_graph(tmp_path))
    again = Runtime(
        tmp_path / "run1",
        source_root=tmp_path,
        mode=Mode.SOLO,
        agents={Phase.P0: EvidenceLedger(owner="ved")},
        critics={},
        phases=phases(critics=frozenset()),
        clock=clock,
        provider=FakeProvider([], usage=USAGE),  # no call may be made
        model="test-model",
    )
    out = again.start(Phase.P0, attempt=2)
    assert out.status == "committed"
    assert store.content_hash(final_graph(tmp_path)) == before


def test_it_runs_in_onboarding_mode_with_no_critic(tmp_path: Path) -> None:
    _corpus.build(tmp_path)
    rt = runtime(tmp_path, mode=Mode.ONBOARDING)
    assert rt.start(Phase.P0).status == "committed"
    g = final_graph(tmp_path)
    (q,) = [
        n for n in g.nodes.values() if isinstance(n, Question) and n.raised_by == "contradiction"
    ]
    assert "wrong" not in q.text.casefold()  # I9: the statements differ; no one is at fault
    rt.close()


def test_a_tampered_source_is_caught_after_the_commit(tmp_path: Path) -> None:
    _corpus.build(tmp_path)
    runtime(tmp_path).start(Phase.P0)
    (tmp_path / "interviews" / "a.md").write_text("Something else entirely.\n")
    codes = {v.code for v in validate_graph(final_graph(tmp_path), source_root=tmp_path)}
    assert "I1_SOURCE_CHANGED" in codes


def test_a_derived_claim_commits_through_the_committer_in_dependency_order(tmp_path: Path) -> None:
    """The Committer settles a chain: the T4 claim reads its parent's number, which is
    itself computed in the same commit."""
    from probative.agents.contract import AgentResult
    from probative.core.evidence import Tier
    from probative.core.graph.edges import Edge
    from probative.graph_runtime.state import GraphState, RunContext
    from probative.ledger.build import new_claim
    from tests.graph_runtime._agents import ScriptedAgent
    from tests.graph_runtime._support import ALL_TIERS, result

    _corpus.build(tmp_path)
    first = runtime(tmp_path)
    first.start(Phase.P0)
    first.close()
    parent = claim_named(final_graph(tmp_path), _corpus.APPROVALS_SLOW)

    def derive(state: GraphState, ctx: RunContext) -> AgentResult:
        child = new_claim("Approvals are slow.", Tier.T1, None, owner="ved", now=ctx.clock())
        # a T4 claim: same builder shape, but derived and with the derived formula
        from probative.core.graph.nodes import Claim
        from probative.core.graph.values import Computed

        t4 = Claim.make(
            text=child.text,
            tier=Tier.T4,
            confidence=Computed(
                value=None, formula_id="claim_confidence_derived", input_ids=["claim_000000000000"]
            ),
            owner="ved",
            asserted_at=ctx.clock(),
        )
        t4 = Claim.model_validate(
            {
                **t4.model_dump(),
                "confidence": Computed(
                    value=None, formula_id="claim_confidence_derived", input_ids=(t4.id,)
                ),
            }
        )
        edge = Edge.make(
            type=EdgeType.DERIVED_FROM,
            src=t4.id,
            dst=parent.id,
            owner="ved",
            asserted_at=ctx.clock(),
        )
        return result([t4], [edge])

    rt = Runtime(
        tmp_path / "run1",
        source_root=tmp_path,
        mode=Mode.SOLO,
        agents={Phase.P1: ScriptedAgent(derive, policy=ALL_TIERS)},
        critics={},
        phases=phases(critics=frozenset()),
        clock=clock,
    )
    assert rt.start(Phase.P1).status == "committed"
    g = final_graph(tmp_path)
    assert claim_named(g, "Approvals are slow.").confidence.value == pytest.approx(0.75 * 0.8)
    assert validate_graph(g, source_root=tmp_path) == []
    assert FormulaValidator().check(g) == []


def test_a_parent_and_its_derived_child_proposed_together_settle_in_one_commit(
    tmp_path: Path,
) -> None:
    """Both numbers are `None` in the patch. A single recompute pass cannot fill the
    child, because its parent has no value yet; the Committer must settle the chain."""
    from probative.agents.contract import AgentResult
    from probative.core.evidence import Tier
    from probative.core.graph.edges import Edge
    from probative.core.graph.nodes import EvidenceSpan
    from probative.core.graph.values import Computed
    from probative.graph_runtime.state import GraphState, RunContext
    from probative.ledger.build import new_claim
    from tests.graph_runtime._agents import ScriptedAgent
    from tests.graph_runtime._support import result

    _corpus.build(tmp_path)
    first = runtime(tmp_path)
    first.start(Phase.P0)
    first.close()
    committed = final_graph(tmp_path)
    existing = next(
        e.dst
        for e in committed.out_edges(
            claim_named(committed, _corpus.SECOND).id, EdgeType.EVIDENCED_BY
        )
    )
    assert isinstance(committed.nodes[existing], EvidenceSpan)

    def both(state: GraphState, ctx: RunContext) -> AgentResult:
        now = ctx.clock()
        parent = new_claim("A second approver is needed.", Tier.T1, None, owner="ved", now=now)
        draft = Claim.make(
            text="Approvals are guarded.",
            tier=Tier.T4,
            confidence=Computed(
                value=None, formula_id="claim_confidence_derived", input_ids=["claim_000000000000"]
            ),
            owner="ved",
            asserted_at=now,
        )
        child = Claim.model_validate(
            {
                **draft.model_dump(),
                "confidence": Computed(
                    value=None, formula_id="claim_confidence_derived", input_ids=(draft.id,)
                ),
            }
        )
        edges = [
            Edge.make(
                type=EdgeType.EVIDENCED_BY,
                src=parent.id,
                dst=existing,
                owner="ved",
                asserted_at=now,
            ),
            Edge.make(
                type=EdgeType.DERIVED_FROM,
                src=child.id,
                dst=parent.id,
                owner="ved",
                asserted_at=now,
            ),
        ]
        return result([parent, child], edges)

    rt = Runtime(
        tmp_path / "run1",
        source_root=tmp_path,
        mode=Mode.SOLO,
        agents={Phase.P1: ScriptedAgent(both)},
        critics={},
        phases=phases(critics=frozenset()),
        clock=clock,
    )
    assert rt.start(Phase.P1).status == "committed"
    g = final_graph(tmp_path)
    assert claim_named(g, "A second approver is needed.").confidence.value == pytest.approx(0.5)
    assert claim_named(g, "Approvals are guarded.").confidence.value == pytest.approx(0.4)
    assert FormulaValidator().check(g) == []
