"""Deterministic dimension scoring (PROBATIVE_PHASE_SPECS.md PB3 "known
unknown", resolved): floor-based, not a weighted mean.

A `block`-severity finding is a veto (docs/DESIGN.md §9.1) and must not be
averaged away by unrelated clean checks in the same rubric, so it collapses
the dimension's score outright rather than merely discounting it.
"""

from __future__ import annotations

from collections.abc import Sequence

from probative.core.critic import DimensionScore, Finding, Rubric, Severity

_CEILING = 10.0
_FLOOR = 0.0
_WARN_PENALTY = 2.0
_NOTE_PENALTY = 0.5


def score_dimension(rubric: Rubric, findings: Sequence[Finding]) -> DimensionScore:
    """Score one rubric's dimension from `findings` (which may include other
    critics' findings — only those with `critic_id == rubric.id` count).

    Any `block`-severity finding among them floors the score at 0.0 and sets
    `blocked`. Otherwise the score starts at a ceiling of 10.0 and is
    discounted 2.0 per `warn` finding and 0.5 per `note` finding, floored at
    0.0 — a `blocked=False` dimension can still reach 0.0 by accumulation,
    which is a different fact from an actual veto and is reported as such.
    """
    own = [f for f in findings if f.critic_id == rubric.id]
    blocked = any(f.severity == Severity.BLOCK for f in own)
    if blocked:
        score = _FLOOR
    else:
        warns = sum(1 for f in own if f.severity == Severity.WARN)
        notes = sum(1 for f in own if f.severity == Severity.NOTE)
        score = max(_FLOOR, _CEILING - _WARN_PENALTY * warns - _NOTE_PENALTY * notes)
    return DimensionScore(
        critic_id=rubric.id,
        invariant=rubric.invariant,
        blocked=blocked,
        score=score,
        findings=own,
    )


def aggregate(rubrics: Sequence[Rubric], findings: Sequence[Finding]) -> list[DimensionScore]:
    """One `DimensionScore` per rubric, in the order `rubrics` was given."""
    return [score_dimension(rubric, findings) for rubric in rubrics]
