from __future__ import annotations

import pytest

from probative.critique.roster import ROSTER
from probative.graph_runtime.modes import ALL_CRITICS, MODES, Mode
from probative.graph_runtime.phases import PHASES, Gate, Phase

ROSTER_IDS = {e.rubric_id for e in ROSTER}


def test_all_critics_is_the_roster() -> None:
    assert set(ALL_CRITICS) == ROSTER_IDS


def test_every_phase_has_a_spec_and_gates_follow_design_9_3() -> None:
    assert set(PHASES) == set(Phase)
    gates = {p: spec.gate for p, spec in PHASES.items()}
    assert gates[Phase.P0] is Gate.G0
    assert gates[Phase.P2] is Gate.G1
    assert gates[Phase.P3] is Gate.G2
    assert gates[Phase.P4] is Gate.G3
    assert gates[Phase.P5] is Gate.G4
    assert gates[Phase.P6] is Gate.G5
    assert gates[Phase.P7] is Gate.G6
    assert gates[Phase.P1] is None


def test_phase_critics_are_known_critics() -> None:
    for spec in PHASES.values():
        assert spec.critics <= ROSTER_IDS


def test_onboarding_omits_the_evaluative_critics_by_config_oi22() -> None:
    omitted = {
        "red_team",
        "segment_skeptic",
        "constraint_critic",
        "dependency_critic",
        "space_warden",
        "invest",
        "evidence_auditor",
    }
    assert not (MODES[Mode.ONBOARDING].critics & omitted)


def test_other_modes_run_every_critic() -> None:
    for mode in (Mode.SOLO, Mode.TEAM, Mode.ENTERPRISE):
        assert MODES[mode].critics == ROSTER_IDS


def test_solo_needs_a_human_at_g1_to_g4_only() -> None:
    solo = MODES[Mode.SOLO]
    assert {Gate.G1, Gate.G2, Gate.G3, Gate.G4} == solo.human_gates
    assert Gate.G0 not in solo.human_gates and Gate.G6 not in solo.human_gates


def test_effective_critics_is_the_intersection() -> None:
    spec = PHASES[Phase.P3]
    assert MODES[Mode.SOLO].effective_critics(spec) == spec.critics
    assert MODES[Mode.ONBOARDING].effective_critics(spec) == frozenset()


def test_unknown_mode_is_an_error() -> None:
    with pytest.raises(ValueError):
        Mode("nope")
