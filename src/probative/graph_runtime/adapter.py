"""Graph nodes as the candidates the critics judge (owner decision, PB12).

Critics (PB3-PB8) judge `Candidate`s, which carry an `EvidenceSpan`. A patch
holds graph nodes. This adapter builds a candidate from a node's *own* text,
with a synthetic span (`source_id` is the node's id, offsets `0..len(text)`),
because a restated `Need` differs from the quote it rests on and a critic reads
the text it is given. Real provenance stays on the node's `EVIDENCED_BY` edge
and is checked by I1 (`validate_graph`), not here.

Consequence, recorded: `EvidenceAuditor` judges the claim's text, not the quote.
A candidate id is derived from the synthetic span, so it is unique per node;
`node_of` maps it back so a finding can be attached to a node.

`RedTeam`'s `ForecastCandidate` has no node type, so it sees nothing in a graph
until one exists (OI26).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from probative.core.candidates import (
    Candidate,
    CandidateKind,
    ClaimCandidate,
    ConstraintCandidate,
    DependencyCandidate,
    NeedCandidate,
    SegmentCandidate,
    StoryCandidate,
    candidate_id,
)
from probative.core.evidence import EvidenceSpan, Locator
from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import (
    Claim,
    Constraint,
    Dependency,
    Need,
    NodeBase,
    Segment,
    Story,
)


@dataclass(frozen=True)
class Found:
    candidates: tuple[Candidate, ...]
    node_of: dict[str, str]


def _text(node: NodeBase) -> str | None:
    if isinstance(node, Claim | Need | Story | Constraint | Dependency):
        return node.text
    if isinstance(node, Segment):
        return f"{node.name}: {node.description}" if node.description else node.name
    return None


def _build(node: NodeBase, text: str) -> Candidate | None:
    span = EvidenceSpan(source_id=node.id, start=0, end=len(text), text=text, locator=Locator())
    kind: CandidateKind
    if isinstance(node, Claim):
        kind = CandidateKind.CLAIM
        return ClaimCandidate(id=candidate_id(kind, span), evidence=span)
    if isinstance(node, Need):
        kind = CandidateKind.NEED
        return NeedCandidate(id=candidate_id(kind, span), evidence=span)
    if isinstance(node, Story):
        kind = CandidateKind.STORY
        return StoryCandidate(id=candidate_id(kind, span), evidence=span)
    if isinstance(node, Constraint):
        kind = CandidateKind.CONSTRAINT
        return ConstraintCandidate(id=candidate_id(kind, span), evidence=span)
    if isinstance(node, Dependency):
        kind = CandidateKind.DEPENDENCY
        return DependencyCandidate(id=candidate_id(kind, span), evidence=span)
    if isinstance(node, Segment):
        kind = CandidateKind.SEGMENT
        return SegmentCandidate(id=candidate_id(kind, span), evidence=span)
    return None


def candidates_for(
    graph: Graph, node_ids: Iterable[str], *, with_traced_stories: bool = False
) -> Found:
    """Candidates for the named nodes, in node-id order.

    `with_traced_stories` adds the stories that point at a named constraint with
    `CONSTRAINED_BY`: `ConstraintCritic` needs them to judge tracing (the roster's
    `feeds`). They are for that critic only; other critics must not receive them.
    """
    ids = sorted(set(node_ids))
    if with_traced_stories:
        extra: set[str] = set()
        for node_id in ids:
            if isinstance(graph.nodes.get(node_id), Constraint):
                extra.update(
                    e.src
                    for e in graph.in_edges(node_id, EdgeType.CONSTRAINED_BY)
                    if isinstance(graph.nodes.get(e.src), Story)
                )
        ids = sorted(set(ids) | extra)
    candidates: list[Candidate] = []
    node_of: dict[str, str] = {}
    for node_id in ids:
        node = graph.nodes.get(node_id)
        text = _text(node) if node is not None else None
        if node is None or text is None:
            continue
        cand = _build(node, text)
        if cand is not None:
            candidates.append(cand)
            node_of[cand.id] = node.id
    return Found(tuple(candidates), node_of)
