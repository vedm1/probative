from __future__ import annotations

from probative.core.candidates import (
    ClaimCandidate,
    ConstraintCandidate,
    DependencyCandidate,
    NeedCandidate,
    SegmentCandidate,
    StoryCandidate,
)
from probative.core.evidence import Locator, Tier
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, Constraint, Dependency, Need, Segment, Story
from probative.graph_runtime.adapter import candidates_for
from tests.core.graph._samples import ENV, conf
from tests.graph_runtime._support import NOW


def graph_of(*nodes, edges=()) -> Graph:  # type: ignore[no-untyped-def]
    return Graph.empty().with_patch(nodes=list(nodes), edges=list(edges))


def test_each_node_type_maps_to_its_candidate_class() -> None:
    claim = Claim.make(text="Users wait.", tier=Tier.T1, confidence=conf(), **ENV)
    need = Need.make(text="Help me see where my money went", **ENV)
    story = Story.make(text="As a clerk I can approve", **ENV)
    constraint = Constraint.make(
        text="Keep records 7 years",
        constraint_kind="regulatory",
        source_doc="p.pdf",
        locator=Locator(page=1),
        **ENV,
    )
    dependency = Dependency.make(text="Needs the billing API", dependency_class="system", **ENV)
    segment = Segment.make(name="Clerks", description="Approve invoices daily", **ENV)
    nodes = [claim, need, story, constraint, dependency, segment]
    found = candidates_for(graph_of(*nodes), [n.id for n in nodes])
    kinds = {type(c) for c in found.candidates}
    assert kinds == {
        ClaimCandidate,
        NeedCandidate,
        StoryCandidate,
        ConstraintCandidate,
        DependencyCandidate,
        SegmentCandidate,
    }


def test_the_candidate_text_is_the_nodes_own_text_not_its_quote() -> None:
    need = Need.make(text="Reduce the time I spend re-keying data", **ENV)
    found = candidates_for(graph_of(need), [need.id])
    (cand,) = found.candidates
    assert cand.text == need.text


def test_the_synthetic_span_is_coherent_and_ids_round_trip_to_nodes() -> None:
    a = Need.make(text="Reduce the time I spend re-keying data", **ENV)
    b = Need.make(text="Know when my approval is overdue", **ENV)
    found = candidates_for(graph_of(a, b), [a.id, b.id])
    assert len({c.id for c in found.candidates}) == 2
    for c in found.candidates:
        assert c.evidence.start == 0 and c.evidence.end == len(c.evidence.text)
    assert {found.node_of[c.id] for c in found.candidates} == {a.id, b.id}


def test_a_segment_text_joins_name_and_description() -> None:
    seg = Segment.make(name="Clerks", description="Approve invoices daily", **ENV)
    (cand,) = candidates_for(graph_of(seg), [seg.id]).candidates
    assert cand.text == "Clerks: Approve invoices daily"
    bare = Segment.make(name="Auditors", **ENV)
    (cand2,) = candidates_for(graph_of(bare), [bare.id]).candidates
    assert cand2.text == "Auditors"


def test_nodes_without_a_critic_view_are_skipped() -> None:
    from probative.core.graph.nodes import Decision

    d = Decision.make(statement="Go", rationale="Because", **ENV)
    assert candidates_for(graph_of(d), [d.id]).candidates == ()


def test_stories_that_trace_to_a_patch_constraint_are_extra_for_constraint_critic() -> None:
    constraint = Constraint.make(
        text="Keep records 7 years",
        constraint_kind="regulatory",
        source_doc="p.pdf",
        locator=Locator(page=1),
        **ENV,
    )
    story = Story.make(text="As a clerk I archive a record", **ENV)
    edge = Edge.make(
        type=EdgeType.CONSTRAINED_BY, src=story.id, dst=constraint.id, owner="ved", asserted_at=NOW
    )
    g = graph_of(constraint, story, edges=[edge])
    plain = candidates_for(g, [constraint.id])
    assert {type(c) for c in plain.candidates} == {ConstraintCandidate}
    fed = candidates_for(g, [constraint.id], with_traced_stories=True)
    assert {type(c) for c in fed.candidates} == {ConstraintCandidate, StoryCandidate}
    assert (
        fed.node_of[next(c.id for c in fed.candidates if isinstance(c, StoryCandidate))] == story.id
    )
