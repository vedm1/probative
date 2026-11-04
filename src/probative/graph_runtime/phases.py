"""The phase table (docs/DESIGN.md §9.2, §9.3) as data.

No producer is registered here. Producers arrive with PB13-PB26 and are handed
to the `Runtime`; the table says only what each phase is allowed and owed.

The token and wall-clock budgets and the interaction budgets are **provisional
configuration, not measurements** (nothing has run yet to measure). They are
integers and seconds of configuration, not graph values, so I4 does not apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Phase(StrEnum):
    P0 = "P0"  # ingest + evidence sufficiency
    P1 = "P1"  # as-is process model (brownfield only)
    P2 = "P2"  # segment + proto-persona
    P3 = "P3"  # needs, ladders, hierarchy, ratings
    P4 = "P4"  # value proposition + refusal list
    P5 = "P5"  # features, ROI, MVP, dependencies, constraints, premortem
    P6 = "P6"  # story map + stories + acceptance criteria
    P7 = "P7"  # to-be process model + phase plan


class Gate(StrEnum):
    G0 = "G0"
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"
    G4 = "G4"
    G5 = "G5"
    G6 = "G6"


@dataclass(frozen=True)
class PhaseSpec:
    phase: Phase
    gate: Gate | None
    critics: frozenset[str]
    token_budget: int
    wall_seconds: float
    interaction_budget: int


_EVIDENCE = "evidence_auditor"


def _spec(phase: Phase, gate: Gate | None, *critics: str, interactions: int = 2) -> PhaseSpec:
    return PhaseSpec(
        phase=phase,
        gate=gate,
        critics=frozenset(critics),
        token_budget=200_000,
        wall_seconds=1800.0,
        interaction_budget=interactions,
    )


PHASES: dict[Phase, PhaseSpec] = {
    Phase.P0: _spec(Phase.P0, Gate.G0, _EVIDENCE, interactions=0),
    Phase.P1: _spec(Phase.P1, None, _EVIDENCE, interactions=0),
    Phase.P2: _spec(Phase.P2, Gate.G1, _EVIDENCE, "segment_skeptic"),
    Phase.P3: _spec(Phase.P3, Gate.G2, _EVIDENCE, "space_warden"),
    Phase.P4: _spec(Phase.P4, Gate.G3, _EVIDENCE, "red_team"),
    Phase.P5: _spec(
        Phase.P5, Gate.G4, _EVIDENCE, "constraint_critic", "dependency_critic", "red_team"
    ),
    Phase.P6: _spec(Phase.P6, Gate.G5, "invest"),
    Phase.P7: _spec(Phase.P7, Gate.G6, _EVIDENCE, interactions=1),
}
