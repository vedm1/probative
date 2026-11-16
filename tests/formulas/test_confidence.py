"""PB13: `claim_confidence_direct` / `claim_confidence_derived` (DESIGN §5.3).

The constants are provisional policy with no published source (OI38), so the
table below is an *independent literal copy* of the spec's table: a change to a
constant, a cap or the shape fails here until both are changed on purpose.
"""

from __future__ import annotations

import pytest

import probative.formulas  # noqa: F401  (registers the formulas)
from probative.core.evidence import EvidenceKind, Locator, SourceFormat, Tier
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, NodeBase, Source
from probative.core.graph.validators import Violation
from probative.core.graph.values import Computed
from probative.formulas import confidence as conf
from probative.formulas.registry import REGISTRY, FormulaInputError
from probative.formulas.validator import FormulaValidator
from tests.core.graph._samples import ENV

DIRECT = "claim_confidence_direct"
DERIVED = "claim_confidence_derived"

# tier -> (weight, cap, {n: expected}) -- spec table, computed by hand
TABLE: dict[Tier, tuple[float, float, dict[int, float]]] = {
    Tier.T1: (0.50, 0.95, {1: 0.5, 2: 0.75, 3: 0.875, 5: 0.95}),
    Tier.T2: (0.35, 0.85, {1: 0.35, 2: 0.5775, 3: 0.725375, 5: 0.85}),
    Tier.T3: (0.30, 0.70, {1: 0.30, 2: 0.51, 3: 0.657, 5: 0.70}),
    Tier.T5: (0.10, 0.30, {1: 0.10, 2: 0.19, 3: 0.271, 5: 0.30}),
}


def codes(vs: list[Violation]) -> list[str]:
    return [v.code for v in vs]


# -- the pure functions ---------------------------------------------------------


@pytest.mark.parametrize(
    ("tier", "n", "expected"),
    [(t, n, e) for t, (_, _, row) in TABLE.items() for n, e in row.items()],
)
def test_direct_confidence_matches_the_spec_table(tier: Tier, n: int, expected: float) -> None:
    w, cap, _ = TABLE[tier]
    assert conf.claim_confidence_direct(w, cap, float(n)) == pytest.approx(expected, abs=1e-12)
    assert conf.WEIGHT[tier.value] == w
    assert conf.CAP[tier.value] == cap


def test_t4_has_no_direct_weight_and_decay_is_point_eight() -> None:
    assert Tier.T4.value not in conf.WEIGHT
    assert Tier.T4.value not in conf.CAP
    assert conf.T4_DECAY == 0.8


@pytest.mark.parametrize(
    ("parents", "expected"), [(0.75, 0.60), (0.95, 0.76), (0.40, 0.32), (1.0, 0.8), (0.0, 0.0)]
)
def test_derived_confidence_is_the_weakest_parent_times_decay(
    parents: float, expected: float
) -> None:
    assert conf.claim_confidence_derived(parents, 0.8) == pytest.approx(expected, abs=1e-12)


def test_direct_confidence_is_monotone_in_n_and_never_above_the_cap() -> None:
    for w, cap, _ in TABLE.values():
        values = [conf.claim_confidence_direct(w, cap, float(n)) for n in range(1, 40)]
        assert values == sorted(values)
        assert max(values) <= cap


def test_a_derived_claim_is_strictly_below_its_weakest_parent() -> None:
    for p in (0.05, 0.3, 0.5, 0.95, 1.0):
        assert conf.claim_confidence_derived(p, conf.T4_DECAY) < p


@pytest.mark.parametrize(
    "args",
    [
        (0.0, 0.9, 1.0),  # weight must be in (0, 1)
        (1.0, 0.9, 1.0),
        (0.5, 0.0, 1.0),  # cap in (0, 1]
        (0.5, 1.5, 1.0),
        (0.5, 0.9, 0.0),  # n at least 1
        (0.5, 0.9, 1.5),  # n whole
        (0.5, 0.9, float("nan")),
        (0.5, 0.9, float("inf")),
    ],
)
def test_direct_domain_errors(args: tuple[float, float, float]) -> None:
    with pytest.raises(FormulaInputError):
        conf.claim_confidence_direct(*args)


@pytest.mark.parametrize(
    "args", [(-0.1, 0.8), (1.1, 0.8), (0.5, 0.0), (0.5, 1.1), (float("nan"), 0.8)]
)
def test_derived_domain_errors(args: tuple[float, float]) -> None:
    with pytest.raises(FormulaInputError):
        conf.claim_confidence_derived(*args)


def test_the_formulas_are_registered_as_probative_constructs_with_a_citation() -> None:
    for fid in (DIRECT, DERIVED):
        f = REGISTRY.get(fid)
        assert f.construct == "probative"
        assert f.fact is not None and f.slots is None
        assert "OI38" in f.citation


# -- graph builders --------------------------------------------------------------


def _claim(text: str, tier: Tier, formula: str, value: float | None) -> Claim:
    first = Claim.make(
        text=text,
        tier=tier,
        confidence=Computed(value=value, formula_id=formula, input_ids=["claim_000000000000"]),
        **ENV,
    )
    return Claim.model_validate(
        {
            **first.model_dump(),
            "confidence": Computed(value=value, formula_id=formula, input_ids=[first.id]),
        }
    )


def _source(char: str, tier: Tier) -> Source:
    return Source.make(
        sha256=char * 64,
        ingest_id="src_" + char * 16,
        format=SourceFormat.MARKDOWN,
        tier=tier,
        kind=EvidenceKind.CUSTOMER,
        extractor="markdown",
        extractor_version="md/1",
        path=f"{char}.md",
        **ENV,
    )


def _span(src: Source, start: int = 0, text: str = "hello") -> EvidenceSpan:
    return EvidenceSpan.make(
        source_ref=src.id,
        start=start,
        end=start + len(text),
        text=text,
        locator=Locator(line=1),
        **ENV,
    )


def _edge(kind: EdgeType, src: NodeBase, dst: NodeBase) -> Edge:
    return Edge.make(type=kind, src=src.id, dst=dst.id, **ENV)


def direct_world(tier: Tier, chars: str, spans_per_source: int = 1) -> tuple[Graph, Claim]:
    claim = _claim("Approvals take days.", tier, DIRECT, None)
    nodes: list[NodeBase] = [claim]
    edges: list[Edge] = []
    for char in chars:
        src = _source(char, tier)
        nodes.append(src)
        for i in range(spans_per_source):
            span = _span(src, start=i * 10, text=f"quote{i}")
            nodes.append(span)
            edges.append(_edge(EdgeType.EVIDENCED_BY, claim, span))
    return Graph.empty().with_patch(nodes=nodes, edges=edges), claim


def stored(graph: Graph, claim: Claim) -> float | bool | None:
    node = graph.nodes[claim.id]
    assert isinstance(node, Claim)
    return node.confidence.value


# -- independence is recomputed from the edges ------------------------------------


@pytest.mark.parametrize(("chars", "expected"), [("a", 0.5), ("ab", 0.75), ("abc", 0.875)])
def test_each_distinct_source_adds_corroboration(chars: str, expected: float) -> None:
    g, claim = direct_world(Tier.T1, chars)
    settled = FormulaValidator().settle(g)
    assert stored(settled, claim) == pytest.approx(expected)
    assert FormulaValidator().check(settled) == []


def test_three_quotes_from_one_source_count_once() -> None:
    g, claim = direct_world(Tier.T1, "a", spans_per_source=3)
    assert stored(FormulaValidator().settle(g), claim) == pytest.approx(0.5)


def test_the_same_bytes_under_two_paths_count_once() -> None:
    claim = _claim("Approvals take days.", Tier.T1, DIRECT, None)
    s1 = _source("a", Tier.T1)
    s2 = Source.make(
        sha256="a" * 64,
        ingest_id="src_" + "a" * 16,
        format=SourceFormat.MARKDOWN,
        tier=Tier.T1,
        kind=EvidenceKind.CUSTOMER,
        extractor="markdown",
        extractor_version="md/1",
        path="copy/a.md",
        **ENV,
    )
    p1, p2 = _span(s1), _span(s2)
    g = Graph.empty().with_patch(
        nodes=[claim, s1, s2, p1, p2],
        edges=[_edge(EdgeType.EVIDENCED_BY, claim, p1), _edge(EdgeType.EVIDENCED_BY, claim, p2)],
    )
    assert stored(FormulaValidator().settle(g), claim) == pytest.approx(0.5)


def test_a_hand_set_number_is_a_mismatch_and_settle_replaces_it() -> None:
    g, claim = direct_world(Tier.T1, "ab")
    g = g.with_recomputed(
        {claim.id: {"confidence": Computed(value=0.99, formula_id=DIRECT, input_ids=(claim.id,))}}
    )
    assert codes(FormulaValidator().check(g)) == ["I4_VALUE_MISMATCH"]
    assert stored(FormulaValidator().settle(g), claim) == pytest.approx(0.75)


def test_a_none_value_is_a_value_type_violation_until_settled() -> None:
    g, _ = direct_world(Tier.T1, "a")
    assert codes(FormulaValidator().check(g)) == ["I4_VALUE_TYPE"]


def test_the_wrong_formula_for_the_tier_is_refused() -> None:
    claim = _claim("Approvals take days.", Tier.T1, DERIVED, 0.5)
    src = _source("a", Tier.T1)
    span = _span(src)
    g = Graph.empty().with_patch(
        nodes=[claim, src, span], edges=[_edge(EdgeType.EVIDENCED_BY, claim, span)]
    )
    assert codes(FormulaValidator().check(g)) == ["I4_INPUT_TYPE"]
    direct_on_t4 = _claim("Derived.", Tier.T4, DIRECT, 0.5)
    assert codes(FormulaValidator().check(Graph.empty().with_patch(nodes=[direct_on_t4]))) == [
        "I4_INPUT_TYPE"
    ]


def test_a_fact_formula_reads_only_its_own_claim() -> None:
    """`other` has a valid basis of its own (0.5), but its Computed points at a claim
    worth 0.875 and stores that. Without the own-node rule the number would match."""
    g, claim = direct_world(Tier.T1, "abc")
    other = _claim("Another statement entirely.", Tier.T1, DIRECT, 0.875)
    other = Claim.model_validate(
        {
            **other.model_dump(),
            "confidence": Computed(value=0.875, formula_id=DIRECT, input_ids=(claim.id,)),
        }
    )
    src = _source("d", Tier.T1)
    span = _span(src)
    g = g.with_patch(nodes=[other, src, span], edges=[_edge(EdgeType.EVIDENCED_BY, other, span)])
    found = FormulaValidator().check(FormulaValidator().settle(g))
    assert [(v.code, v.node_id) for v in found] == [("I4_INPUT_TYPE", other.id)]
    assert "its own node" in found[0].message


def test_a_claim_with_no_spans_is_unreadable_not_a_number() -> None:
    claim = _claim("Orphan.", Tier.T1, DIRECT, 0.5)
    g = Graph.empty().with_patch(nodes=[claim])
    assert codes(FormulaValidator().check(g)) == ["I4_INPUT_TYPE"]  # I1 names the orphan


def test_two_input_ids_are_an_arity_error() -> None:
    g, claim = direct_world(Tier.T1, "a")
    bad = Computed(value=0.5, formula_id=DIRECT, input_ids=(claim.id, claim.id))
    g = g.with_recomputed({claim.id: {"confidence": bad}})
    assert codes(FormulaValidator().check(g)) == ["I4_INPUT_ARITY"]


# -- derived (T4) and the settle loop --------------------------------------------


def chain(depth: int) -> tuple[Graph, list[Claim]]:
    """A T1 claim (two sources: 0.75) with `depth` T4 claims, each derived from the one before."""
    base, root = direct_world(Tier.T1, "ab")
    claims = [root]
    nodes: list[NodeBase] = []
    edges: list[Edge] = []
    for i in range(depth):
        child = _claim(f"Inference number {i}.", Tier.T4, DERIVED, None)
        nodes.append(child)
        edges.append(_edge(EdgeType.DERIVED_FROM, child, claims[-1]))
        claims.append(child)
    return base.with_patch(nodes=nodes, edges=edges), claims


def test_settle_fixes_a_three_deep_chain_in_dependency_order() -> None:
    g, claims = chain(3)
    settled = FormulaValidator().settle(g)
    values = [stored(settled, c) for c in claims]
    assert values == pytest.approx([0.75, 0.6, 0.48, 0.384])
    assert FormulaValidator().check(settled) == []


def test_one_pass_recompute_cannot_fix_a_child_of_a_none_parent() -> None:
    g, claims = chain(1)
    fixes = FormulaValidator().recompute(g)
    assert set(fixes) == {claims[0].id}  # the child waits for its parent
    assert "I4_INPUT_PENDING" in codes(FormulaValidator().check(g))


def test_a_derived_claim_takes_the_weakest_of_several_parents() -> None:
    g, claims = chain(0)
    weak = _claim("A weaker statement.", Tier.T1, DIRECT, None)
    src = _source("c", Tier.T1)
    span = _span(src)
    child = _claim("Inference.", Tier.T4, DERIVED, None)
    g = g.with_patch(
        nodes=[weak, src, span, child],
        edges=[
            _edge(EdgeType.EVIDENCED_BY, weak, span),
            _edge(EdgeType.DERIVED_FROM, child, claims[0]),
            _edge(EdgeType.DERIVED_FROM, child, weak),
        ],
    )
    settled = FormulaValidator().settle(g)
    assert stored(settled, child) == pytest.approx(0.5 * 0.8)


def test_a_t4_claim_with_no_claim_parent_is_unreadable() -> None:
    child = _claim("Inference.", Tier.T4, DERIVED, 0.5)
    assert codes(FormulaValidator().check(Graph.empty().with_patch(nodes=[child]))) == [
        "I4_INPUT_TYPE"
    ]


def test_settle_leaves_a_clean_graph_untouched() -> None:
    g, _ = chain(2)
    settled = FormulaValidator().settle(g)
    assert FormulaValidator().settle(settled) is settled


def test_settle_is_bounded() -> None:
    from probative.formulas.validator import RecomputeDivergedError

    g, _ = chain(1)

    class Flapping(FormulaValidator):
        def recompute(self, graph: Graph) -> dict[str, dict[str, Computed]]:
            claim = next(iter(n for n in graph.nodes.values() if isinstance(n, Claim)))
            value = 0.1 if claim.confidence.value != 0.1 else 0.2
            return {claim.id: {"confidence": claim.confidence.model_copy(update={"value": value})}}

    with pytest.raises(RecomputeDivergedError, match="I4_RECOMPUTE_DIVERGED"):
        Flapping().settle(g)
