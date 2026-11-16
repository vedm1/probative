"""PB13: candidates to graph nodes, dedupe, corroboration, and the I1 round trip."""

from __future__ import annotations

from pathlib import Path

import pytest

import probative.formulas  # noqa: F401  (registers the formulas)
from probative.core.evidence import EvidenceKind, Tier
from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, NodeBase
from probative.core.graph.nodes import Source as SourceNode
from probative.core.graph.validators import validate_graph
from probative.formulas.validator import FormulaValidator
from probative.ledger.build import claim_patch, new_claim, source_node
from probative.ledger.independence import independent_sources
from tests.ledger._helpers import NOW, OWNER, claims_of, ingest_file


def graph_of(root: Path, *files: tuple[str, str, tuple[str, ...]]) -> tuple[Graph, list[Claim]]:
    graph = Graph.empty()
    for rel, text, quotes in files:
        core = ingest_file(root, rel, text)
        node = source_node(core, root, owner=OWNER, now=NOW)
        nodes, edges = claim_patch(node, core, claims_of(core, *quotes), owner=OWNER, now=NOW)
        graph = graph.with_patch(nodes=[node, *nodes], edges=edges)
    return graph, [n for n in graph.nodes.values() if isinstance(n, Claim)]


def settled(graph: Graph) -> Graph:
    return FormulaValidator().settle(graph)


def test_a_source_node_carries_a_relative_path_and_the_ingest_identity(tmp_path: Path) -> None:
    core = ingest_file(tmp_path, "interviews/a.md", "Approvals take days.\n")
    node = source_node(core, tmp_path, owner=OWNER, now=NOW)
    assert isinstance(node, SourceNode)
    assert node.path == "interviews/a.md"
    assert node.ingest_id == core.id and node.sha256 == core.sha256
    assert (node.tier, node.kind) == (Tier.T1, EvidenceKind.CUSTOMER)


def test_a_source_outside_the_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    core = ingest_file(tmp_path, "elsewhere/a.md", "Approvals take days.\n")
    with pytest.raises(ValueError, match="outside"):
        source_node(core, root, owner=OWNER, now=NOW)


def test_a_claim_copies_tier_and_kind_from_its_source_and_has_no_value_yet(tmp_path: Path) -> None:
    _, claims = graph_of(
        tmp_path, ("interviews/a.md", "Approvals take days.\n", ("Approvals take days.",))
    )
    (claim,) = claims
    assert (claim.tier, claim.evidence_kind) == (Tier.T1, EvidenceKind.CUSTOMER)
    assert claim.confidence.value is None  # I4: the ledger never supplies a number
    assert claim.confidence.formula_id == "claim_confidence_direct"
    assert claim.confidence.input_ids == (claim.id,)


def test_every_span_round_trips_through_reextraction(tmp_path: Path) -> None:
    g, _ = graph_of(
        tmp_path,
        (
            "interviews/a.md",
            "# Notes\n\n- Approvals take days.\n- Managers sign late.\n",
            ("- Approvals take days.", "Managers sign late."),
        ),
    )
    assert [v for v in validate_graph(settled(g), source_root=tmp_path)] == []
    assert FormulaValidator().check(settled(g)) == []


def test_the_claim_text_is_the_normalised_span_not_the_quote(tmp_path: Path) -> None:
    g, claims = graph_of(
        tmp_path,
        ("interviews/a.md", "- Approvals   take days.\n", ("- Approvals   take days.",)),
    )
    (claim,) = claims
    spans = [n for n in g.nodes.values() if isinstance(n, EvidenceSpan)]
    assert spans[0].text == "- Approvals   take days."
    assert claim.text == "Approvals take days."


def test_the_same_statement_in_two_sources_is_one_claim_with_two_spans(tmp_path: Path) -> None:
    g, claims = graph_of(
        tmp_path,
        ("interviews/a.md", "Approvals take days.\n", ("Approvals take days.",)),
        (
            "interviews/b.md",
            "We said:   approvals take days.\n".replace("approvals", "Approvals"),
            ("Approvals take days.",),
        ),
    )
    (claim,) = claims
    assert len(g.out_edges(claim.id, EdgeType.EVIDENCED_BY)) == 2
    assert independent_sources(g, claim.id) == 2
    assert settled(g).nodes[claim.id].confidence.value == pytest.approx(0.75)  # type: ignore[attr-defined]
    assert validate_graph(settled(g), source_root=tmp_path) == []


def test_whitespace_variants_merge_but_case_variants_do_not(tmp_path: Path) -> None:
    _, claims = graph_of(
        tmp_path,
        ("interviews/a.md", "Approvals take days.\n", ("Approvals take days.",)),
        ("interviews/b.md", "Approvals   take\n  days.\n", ("Approvals   take\n  days.",)),
        ("interviews/c.md", "approvals take days.\n", ("approvals take days.",)),
    )
    assert sorted(c.text for c in claims) == ["Approvals take days.", "approvals take days."]


def test_the_same_statement_twice_in_one_source_counts_once(tmp_path: Path) -> None:
    text = "Approvals take days. Later: Approvals take days.\n"
    core = ingest_file(tmp_path, "interviews/a.md", text)
    node = source_node(core, tmp_path, owner=OWNER, now=NOW)
    second = text.rindex("Approvals take days.")
    from probative.core.candidates import (
        CandidateKind,
        ClaimCandidate,
        ExtractionResult,
        candidate_id,
    )
    from probative.ingest import spans

    cands = []
    for start in (0, second):
        sp = spans(core, [(start, start + len("Approvals take days."))])[0]
        cands.append(ClaimCandidate(id=candidate_id(CandidateKind.CLAIM, sp), evidence=sp))
    nodes, edges = claim_patch(
        node, core, ExtractionResult(source_id=core.id, claims=cands), owner=OWNER, now=NOW
    )
    g = Graph.empty().with_patch(nodes=[node, *nodes], edges=edges)
    (claim,) = [n for n in g.nodes.values() if isinstance(n, Claim)]
    assert len(g.out_edges(claim.id, EdgeType.EVIDENCED_BY)) == 2
    assert settled(g).nodes[claim.id].confidence.value == pytest.approx(0.5)  # type: ignore[attr-defined]


def test_the_patch_is_deterministic_and_ordered(tmp_path: Path) -> None:
    core = ingest_file(tmp_path, "interviews/a.md", "One thing. Two things.\n")
    node = source_node(core, tmp_path, owner=OWNER, now=NOW)
    a = claim_patch(node, core, claims_of(core, "One thing.", "Two things."), owner=OWNER, now=NOW)
    b = claim_patch(node, core, claims_of(core, "Two things.", "One thing."), owner=OWNER, now=NOW)
    assert [n.id for n in a[0]] == [n.id for n in b[0]] == sorted(n.id for n in a[0])
    assert [e.id for e in a[1]] == [e.id for e in b[1]]


def test_a_candidate_with_no_words_in_it_is_skipped(tmp_path: Path) -> None:
    core = ingest_file(tmp_path, "interviews/a.md", "Real statement here. - \n")
    node = source_node(core, tmp_path, owner=OWNER, now=NOW)
    nodes, _ = claim_patch(
        node, core, claims_of(core, "Real statement here."), owner=OWNER, now=NOW
    )
    assert len([n for n in nodes if isinstance(n, Claim)]) == 1


def test_new_claim_ids_do_not_depend_on_the_confidence_value() -> None:
    a = new_claim("Approvals take days.", Tier.T1, EvidenceKind.CUSTOMER, owner=OWNER, now=NOW)
    assert a.confidence.input_ids == (a.id,)
    again = new_claim("Approvals take days.", Tier.T1, EvidenceKind.CUSTOMER, owner=OWNER, now=NOW)
    assert again == a


def test_a_t3_claim_uses_the_direct_formula_and_a_t4_cannot_be_built_here() -> None:
    assert (
        new_claim("x y", Tier.T3, None, owner=OWNER, now=NOW).confidence.formula_id
        == "claim_confidence_direct"
    )
    with pytest.raises(ValueError, match="T4"):
        new_claim("x y", Tier.T4, None, owner=OWNER, now=NOW)


def test_independence_still_counts_a_superseded_source(tmp_path: Path) -> None:
    from probative.core.graph.edges import Edge

    g, claims = graph_of(
        tmp_path, ("interviews/a.md", "Approvals take days.\n", ("Approvals take days.",))
    )
    (claim,) = claims
    old = next(n for n in g.nodes.values() if isinstance(n, SourceNode))
    revised = SourceNode.make(
        sha256="b" * 64,
        ingest_id="src_" + "b" * 16,
        format=old.format,
        tier=old.tier,
        kind=old.kind,
        extractor=old.extractor,
        extractor_version=old.extractor_version,
        path="interviews/a2.md",
        owner=OWNER,
        asserted_at=NOW,
    )
    sup = Edge.make(
        type=EdgeType.SUPERSEDES,
        src=revised.id,
        dst=old.id,
        attrs={"reason": "re-issued"},
        owner=OWNER,
        asserted_at=NOW,
    )
    g = g.with_patch(nodes=[revised], edges=[sup])
    assert independent_sources(g, claim.id) == 1  # review S1: the claim stays readable
    assert isinstance(g.nodes[claim.id], NodeBase)
