from __future__ import annotations

import pytest

from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph, GraphIntegrityError
from probative.core.graph.nodes import Need
from tests.core.graph._samples import ENV, all_samples, sample_claim, sample_source, sample_span


def _edge(kind: EdgeType, src: str, dst: str, **attrs: str) -> Edge:
    return Edge.make(type=kind, src=src, dst=dst, attrs=attrs, **ENV)


def _needs(*texts: str) -> list[Need]:
    return [Need.make(text=t, **ENV) for t in texts]


def _supersede(new: Need, old: Need, reason: str = "refined") -> Edge:
    return _edge(EdgeType.SUPERSEDES, new.id, old.id, reason=reason)


def test_with_patch_returns_a_new_graph_and_leaves_the_original_alone() -> None:
    g0 = Graph.empty()
    (n,) = _needs("Reduce time")
    g1 = g0.with_patch(nodes=[n])
    assert len(g0.nodes) == 0 and g1.nodes[n.id] == n


def test_there_is_no_way_to_edit_or_delete() -> None:
    public = {m for m in dir(Graph) if not m.startswith("_")}
    assert not {m for m in public if m.startswith(("update", "delete", "remove", "set", "pop"))}
    g = Graph.empty().with_patch(nodes=_needs("a"))
    with pytest.raises(TypeError):
        g.nodes["x"] = None  # type: ignore[index]


def test_a_repeated_node_is_idempotent() -> None:
    (n,) = _needs("a")
    g = Graph.empty().with_patch(nodes=[n]).with_patch(nodes=[n])
    assert len(g.nodes) == 1


def test_the_same_content_asserted_later_keeps_the_first_assertion() -> None:
    (n,) = _needs("a")
    later = n.model_copy(update={"asserted_at": ENV["asserted_at"].replace(year=2027)})
    g = Graph.empty().with_patch(nodes=[n]).with_patch(nodes=[later])
    assert g.nodes[n.id].asserted_at == n.asserted_at


def test_dangling_edge_endpoint_is_an_integrity_error() -> None:
    a, b = _needs("a", "b")
    e = _edge(EdgeType.REQUIRES, a.id, b.id)
    with pytest.raises(GraphIntegrityError, match="dangling"):
        Graph.empty().with_patch(nodes=[a], edges=[e])


def test_a_bad_endpoint_pair_is_an_integrity_error() -> None:
    s = all_samples()
    e = _edge(EdgeType.EVIDENCED_BY, s["need"].id, s["evidence_span"].id)
    with pytest.raises(GraphIntegrityError, match="EVIDENCED_BY"):
        Graph.empty().with_patch(nodes=[s["need"], s["evidence_span"]], edges=[e])


def test_i3_is_enforced_when_an_edge_is_added() -> None:
    s = all_samples()
    e = _edge(EdgeType.DERIVED_FROM, s["need"].id, s["feature_idea"].id)
    with pytest.raises(GraphIntegrityError, match="I3"):
        Graph.empty().with_patch(nodes=[s["need"], s["feature_idea"]], edges=[e])


def test_a_failed_patch_leaves_no_trace() -> None:
    a, b = _needs("a", "b")
    g = Graph.empty().with_patch(nodes=[a])
    with pytest.raises(GraphIntegrityError):
        g.with_patch(nodes=[b], edges=[_edge(EdgeType.REQUIRES, a.id, "need_ffffffffffff")])
    assert set(g.nodes) == {a.id}


def test_out_and_in_edges() -> None:
    a, b = _needs("a", "b")
    e = _edge(EdgeType.REQUIRES, a.id, b.id)
    g = Graph.empty().with_patch(nodes=[a, b], edges=[e])
    assert g.out_edges(a.id) == [e] and g.in_edges(b.id) == [e]
    assert g.out_edges(a.id, EdgeType.LADDERS_UP_TO) == []


def test_supersession_current_history_and_superseded_by() -> None:
    v1, v2, v3 = _needs("v1", "v2", "v3")
    g = Graph.empty().with_patch(nodes=[v1, v2, v3], edges=[_supersede(v2, v1), _supersede(v3, v2)])
    assert [n.id for n in g.current()] == [v3.id]
    assert g.superseded_by(v1.id) == v2.id and g.superseded_by(v3.id) is None
    assert g.history(v2.id) == [v1.id, v2.id, v3.id]
    assert v1.id in g.nodes  # nothing is ever deleted


def test_supersession_can_arrive_in_a_later_patch() -> None:
    v1, v2 = _needs("v1", "v2")
    g = Graph.empty().with_patch(nodes=[v1]).with_patch(nodes=[v2], edges=[_supersede(v2, v1)])
    assert g.superseded_by(v1.id) == v2.id


def test_a_node_cannot_be_superseded_twice() -> None:
    v1, v2, v3 = _needs("v1", "v2", "v3")
    with pytest.raises(GraphIntegrityError, match="superseded"):
        Graph.empty().with_patch(nodes=[v1, v2, v3], edges=[_supersede(v2, v1), _supersede(v3, v1)])


def test_a_node_cannot_supersede_two() -> None:
    v1, v2, v3 = _needs("v1", "v2", "v3")
    with pytest.raises(GraphIntegrityError, match="supersede"):
        Graph.empty().with_patch(nodes=[v1, v2, v3], edges=[_supersede(v3, v1), _supersede(v3, v2)])


def test_supersession_cycles_are_rejected() -> None:
    v1, v2 = _needs("v1", "v2")
    with pytest.raises(GraphIntegrityError, match="cycle"):
        Graph.empty().with_patch(nodes=[v1, v2], edges=[_supersede(v2, v1), _supersede(v1, v2)])


def test_self_supersession_is_rejected() -> None:
    (v1,) = _needs("v1")
    with pytest.raises(GraphIntegrityError):
        Graph.empty().with_patch(nodes=[v1], edges=[_supersede(v1, v1)])


def test_the_reason_is_kept_on_the_edge() -> None:
    v1, v2 = _needs("v1", "v2")
    g = Graph.empty().with_patch(nodes=[v1, v2], edges=[_supersede(v2, v1, "rating changed")])
    (e,) = g.out_edges(v2.id, EdgeType.SUPERSEDES)
    assert e.attrs["reason"] == "rating changed"


def test_a_realistic_provenance_chain_builds() -> None:
    src = sample_source()
    span = sample_span(src)
    claim = sample_claim()
    g = Graph.empty().with_patch(
        nodes=[src, span, claim], edges=[_edge(EdgeType.EVIDENCED_BY, claim.id, span.id)]
    )
    assert g.out_edges(claim.id, EdgeType.EVIDENCED_BY)[0].dst == span.id
