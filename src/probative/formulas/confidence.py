"""`Claim.confidence` (docs/DESIGN.md §5.3; PB13). A Probative construct.

No book gives these numbers, so the weights, caps and decay below are
**provisional policy** (OI38): named constants, pinned by tests, stated as
provisional in the run header. The *shape* is DESIGN §5.3:

* Corroboration raises confidence, but only from *independent* sources. The
  unit of independence is one distinct file content (`Source.sha256`, OI39):
  three quotes from one transcript count once.
* Derivation caps it: `derived = min(parent confidences) * decay`.
* Contradiction is preserved, never averaged: it does not change a confidence,
  it opens a `Question`.

Direct claim (T1, T2, T3, T5), `n` independent sources of weight `w`, cap `c`:
    confidence = min(c, 1 - (1 - w) ** n)
Derived claim (T4): confidence = min(parents) * decay.

The count `n` is a `GraphFact`: recomputed from the edges on every commit, never
stored, so it cannot be authored (I4). A model may propose the claim and its
evidence; it never produces the number.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from probative.core.evidence import Tier
from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, Source
from probative.formulas.registry import (
    REGISTRY,
    FactResult,
    Formula,
    FormulaInputError,
    GraphFact,
    Pending,
    Unreadable,
)

WEIGHT: Final[Mapping[str, float]] = MappingProxyType(
    {Tier.T1.value: 0.50, Tier.T2.value: 0.35, Tier.T3.value: 0.30, Tier.T5.value: 0.10}
)
"""What one independent source of each tier contributes. Provisional (OI38)."""

CAP: Final[Mapping[str, float]] = MappingProxyType(
    {Tier.T1.value: 0.95, Tier.T2.value: 0.85, Tier.T3.value: 0.70, Tier.T5.value: 0.30}
)
"""The most corroboration can reach for each tier. Provisional (OI38)."""

T4_DECAY: Final = 0.8
"""A derived claim is this fraction of its weakest parent. Provisional (OI38)."""


def _number(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise FormulaInputError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def claim_confidence_direct(weight: float, cap: float, n: float) -> float:
    w, c, count = _number("weight", weight), _number("cap", cap), _number("n", n)
    if not 0 < w < 1:
        raise FormulaInputError(f"weight must be in (0, 1), got {w!r}")
    if not 0 < c <= 1:
        raise FormulaInputError(f"cap must be in (0, 1], got {c!r}")
    if count < 1 or not count.is_integer():
        raise FormulaInputError(f"n must be a whole number of at least 1, got {count!r}")
    return min(c, 1.0 - float((1.0 - w) ** count))


def claim_confidence_derived(parent_min: float, decay: float) -> float:
    p, d = _number("parent_min", parent_min), _number("decay", decay)
    if not 0 <= p <= 1:
        raise FormulaInputError(f"parent_min must be in [0, 1], got {p!r}")
    if not 0 < d <= 1:
        raise FormulaInputError(f"decay must be in (0, 1], got {d!r}")
    return p * d


# -- graph facts ------------------------------------------------------------------


def independent_sources(graph: Graph, claim_id: str) -> int:
    """How many independent sources stand behind a claim: distinct `Source.sha256`
    among its `EVIDENCED_BY` spans. A superseded source still counts: its span still
    resolves, and superseding a file does not retract what a claim quoted from it (the claim
    is superseded on its own if it should go). Review S1: ignoring it left a claim with no
    readable basis that `settle` could not fix and I1 did not report."""
    shas: set[str] = set()
    for edge in graph.out_edges(claim_id, EdgeType.EVIDENCED_BY):
        span = graph.nodes.get(edge.dst)
        source = graph.nodes.get(span.source_ref) if isinstance(span, EvidenceSpan) else None
        if isinstance(source, Source):
            shas.add(source.sha256)
    return len(shas)


_DIRECT_TIERS = frozenset({Tier.T1, Tier.T2, Tier.T3, Tier.T5})


def direct_basis(graph: Graph, claim_id: str) -> FactResult:
    claim = graph.nodes.get(claim_id)
    if not isinstance(claim, Claim):
        return Unreadable(f"{claim_id} is not a claim")
    if claim.tier not in _DIRECT_TIERS:
        return Unreadable(f"a {claim.tier.value} claim rests on parents: use {DERIVED}")
    n = independent_sources(graph, claim_id)
    if n == 0:
        return Unreadable("the claim has no source (I1 reports the orphan)")
    return (WEIGHT[claim.tier.value], CAP[claim.tier.value], float(n))


def derived_basis(graph: Graph, claim_id: str) -> FactResult:
    claim = graph.nodes.get(claim_id)
    if not isinstance(claim, Claim):
        return Unreadable(f"{claim_id} is not a claim")
    if claim.tier is not Tier.T4:
        return Unreadable(f"a {claim.tier.value} claim rests on sources: use {DIRECT}")
    parents = [
        p
        for e in graph.out_edges(claim_id, EdgeType.DERIVED_FROM)
        if isinstance(p := graph.nodes.get(e.dst), Claim)
    ]
    if not parents:
        return Unreadable("the claim derives from no claim (I1 reports the leaf)")
    values: list[float] = []
    for parent in parents:
        stored = parent.confidence.value
        if stored is None:
            return Pending(f"parent {parent.id} has no confidence yet")
        if isinstance(stored, bool) or not isinstance(stored, int | float):
            return Unreadable(f"parent {parent.id} has an unusable confidence")
        if not math.isfinite(stored) or not 0 <= stored <= 1:
            return Unreadable(f"parent {parent.id} has a confidence outside 0 to 1")
        values.append(float(stored))
    return (min(values), T4_DECAY)


DIRECT: Final = "claim_confidence_direct"
DERIVED: Final = "claim_confidence_derived"

REGISTRY.register(
    Formula(
        id=DIRECT,
        fn=claim_confidence_direct,
        slots=None,
        fact=GraphFact("direct_basis", direct_basis),
        target_unit=None,
        citation="DESIGN §5.3; weights and caps provisional, OI38; independence unit OI39",
        construct="probative",
    )
)
REGISTRY.register(
    Formula(
        id=DERIVED,
        fn=claim_confidence_derived,
        slots=None,
        fact=GraphFact("derived_basis", derived_basis),
        target_unit=None,
        citation="DESIGN §5.3; decay provisional, OI38",
        construct="probative",
    )
)
