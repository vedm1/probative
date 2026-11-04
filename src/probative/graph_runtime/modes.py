"""Run modes as data (docs/DESIGN.md §9.6; OI22; I9).

A mode lists the critics it runs and the gates that need a person. Excluding a
critic in onboarding mode is a property of this table, not a request in a
prompt: the `Runtime` refuses to be built with a critic the mode omits, and
`effective_critics` can only narrow what a phase asks for.

**Onboarding runs no roster critic (provisional, owner-approved with PB12).**
`red_team`, `segment_skeptic`, `constraint_critic` and `dependency_critic`
judge how a past author framed, traced or owned something. The other three
(`space_warden`, `invest`, `evidence_auditor`) would grade reconstructed claims
as someone's work. The deterministic validators (I1, I2, I4) still run in every
mode, because they judge structure, not people.

**Team gate policy is an assumption.** DESIGN §9.3 has Solo and Enterprise
columns only. Team is set to the enterprise human gates (no sign-off step is
built, so "human + sign-off" is "human").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from probative.graph_runtime.phases import Gate, PhaseSpec

ALL_CRITICS: frozenset[str] = frozenset(
    {
        "evidence_auditor",
        "space_warden",
        "segment_skeptic",
        "invest",
        "dependency_critic",
        "constraint_critic",
        "red_team",
    }
)
"""The rubric ids of `probative.critique.roster.ROSTER` (a test pins equality)."""


class Mode(StrEnum):
    SOLO = "solo"
    TEAM = "team"
    ENTERPRISE = "enterprise"
    ONBOARDING = "onboarding"


@dataclass(frozen=True)
class ModeConfig:
    mode: Mode
    critics: frozenset[str]
    human_gates: frozenset[Gate]

    def effective_critics(self, spec: PhaseSpec) -> frozenset[str]:
        return spec.critics & self.critics

    def needs_human(self, gate: Gate | None) -> bool:
        return gate is not None and gate in self.human_gates


_SOLO_GATES = frozenset({Gate.G1, Gate.G2, Gate.G3, Gate.G4})
_FULL_GATES = frozenset({Gate.G1, Gate.G2, Gate.G3, Gate.G4, Gate.G5, Gate.G6})

MODES: dict[Mode, ModeConfig] = {
    Mode.SOLO: ModeConfig(Mode.SOLO, ALL_CRITICS, _SOLO_GATES),
    Mode.TEAM: ModeConfig(Mode.TEAM, ALL_CRITICS, _FULL_GATES),
    Mode.ENTERPRISE: ModeConfig(Mode.ENTERPRISE, ALL_CRITICS, _FULL_GATES),
    Mode.ONBOARDING: ModeConfig(Mode.ONBOARDING, frozenset(), _SOLO_GATES),
}
