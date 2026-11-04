"""Shared builders for the runtime tests. Synthetic data only."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from probative.agents.contract import AgentResult, CostRecord, SelfAssessment, TierPolicy
from probative.core.evidence import EvidenceKind, Tier
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import (
    Hypothesis,
    NodeBase,
    Opportunity,
    Rating,
    Test,
)
from probative.core.graph.values import Computed
from tests.core.graph._samples import ENV, inp, sample_test

NOW = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
ALL_TIERS = TierPolicy(allowed=frozenset(Tier))


def clock() -> datetime:
    return NOW


def result(
    nodes: list[NodeBase] | None = None,
    edges: list[Edge] | None = None,
    *,
    tokens: int = 10,
) -> AgentResult:
    return AgentResult(
        proposed_nodes=tuple(nodes or ()),  # type: ignore[arg-type]
        proposed_edges=tuple(edges or ()),
        tool_calls=(),
        rationale="scripted",
        self_assessment=SelfAssessment(least_sure_about=()),
        cost=CostRecord(input_tokens=tokens, output_tokens=0, wall_seconds=0.0),
    )


def rating(dimension: str, value: float, unit: str = "scale_0_10") -> Rating:
    return Rating.make(
        dimension=dimension,
        value=inp(value, unit),
        n=inp(12),
        dispersion=inp(1.0, "stdev"),
        tier=Tier.T1,
        evidence_kind=EvidenceKind.CUSTOMER,
        **ENV,
    )


def opportunity(inputs: list[Rating], value: float | None = None) -> Opportunity:
    return Opportunity.make(
        value=Computed(
            value=value, formula_id="ulwick_opportunity", input_ids=[r.id for r in inputs]
        ),
        **ENV,
    )


def good_ratings() -> tuple[Rating, Rating]:
    """Olsen p. 57: importance 10, satisfaction 5 gives an opportunity of 15."""
    return rating("importance", 10), rating("satisfaction", 5)


def hypothesis_with_test() -> tuple[list[NodeBase], list[Edge]]:
    h = Hypothesis.make(statement="Users want faster approvals", tier=Tier.T3, **ENV)
    t: Test = sample_test()
    e = Edge.make(type=EdgeType.TESTED_BY, src=h.id, dst=t.id, owner="ved", asserted_at=NOW)
    return [h, t], [e]


def empty_graph() -> Graph:
    return Graph.empty()


def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run1"
    d.mkdir()
    return d
