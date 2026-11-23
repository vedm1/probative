"""Information gain (PB14): did an answer change the graph?

A pure comparison of two graphs, no model and no tokens, so it can run between
questions. It is a stopping rule, not a number on a node (I4): counts, and one sum of
absolute differences of values the registry already computed. A turn is *wasted* when it
adds no claim, moves no confidence, closes no open Question and raises no contradiction.
An `unknown` opens a Question; that is a recorded gap and is not counted as gain.

Limit (spec, "Information gain"): at PB14 the only downstream values are `Claim.confidence`
and Questions, and one transcript gives each of its claims the same single-source
confidence, so `new_claims` does most of the work. Needs and ratings (PB17-18) widen it.
"""

from __future__ import annotations

from collections.abc import Sequence

from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, Question
from probative.elicit.types import GainReport


def _claims(graph: Graph) -> dict[str, float | None]:
    found: dict[str, float | None] = {}
    for node in graph.current():
        if isinstance(node, Claim):
            value = node.confidence.value
            found[node.id] = (
                float(value)
                if isinstance(value, int | float) and not isinstance(value, bool)
                else None
            )
    return found


def _open_questions(graph: Graph) -> set[str]:
    return {n.id for n in graph.current() if isinstance(n, Question) and n.status == "open"}


def _contradictions(graph: Graph) -> set[str]:
    return {e.id for e in graph.edges.values() if e.type is EdgeType.CONTRADICTS}


def measure(before: Graph, after: Graph) -> GainReport:
    claims_before, claims_after = _claims(before), _claims(after)
    delta = 0.0
    for claim_id, value in claims_before.items():
        later = claims_after.get(claim_id)
        if value is not None and later is not None:
            delta += abs(later - value)
    open_before, open_after = _open_questions(before), _open_questions(after)
    return GainReport(
        new_claims=len(claims_after.keys() - claims_before.keys()),
        confidence_delta=delta,
        questions_closed=len(open_before - open_after),
        contradictions=len(_contradictions(after) - _contradictions(before)),
        questions_opened=len(open_after - open_before),
    )


def should_stop(rounds: Sequence[Sequence[GainReport]], quiet_rounds: int) -> bool:
    """Stop after `quiet_rounds` consecutive rounds in which every turn was wasted. An
    empty round counts as quiet: nothing was asked, nothing was gained."""
    if len(rounds) < quiet_rounds:
        return False
    return all(all(r.wasted for r in rnd) for rnd in rounds[-quiet_rounds:])
