"""Deterministic report numbers (OI18, resolved in PB9; I4).

PB3's `score_dimension` is a veto-shaped floor and does not depend on how many
candidates were checked, so it cannot say how conforming a document is. The
report therefore carries a rate beside it: of the candidates a critic examined,
how many drew no block or warn finding. Notes do not flag. Several findings on
one candidate flag it once.

A dimension that examined nothing is `not_applicable`, never a clean 10.
A dimension with a candidate that could not be judged is `incomplete` and has
no rate: a rate over the part that was judged would read as a verdict.

Formula ids are recorded here until PB11's registry exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from probative.core.critic import Finding, Rubric, Severity
from probative.critics.scoring import score_dimension
from probative.critique.report import (
    DimensionResult,
    DimensionStatus,
    ReportFinding,
    SeverityCounts,
)

FORMULA_CLEAN_RATE: Final = "critique.clean_rate"
FORMULA_FLAGGED: Final = "critique.flagged"

_FLAGGING = (Severity.BLOCK, Severity.WARN)


def flagged_candidates(findings: Sequence[Finding | ReportFinding]) -> int:
    """Distinct candidates with at least one block or warn finding."""
    return len({f.target_id for f in findings if f.severity in _FLAGGING})


def severity_counts(findings: Sequence[Finding | ReportFinding]) -> SeverityCounts:
    return SeverityCounts(
        block=sum(1 for f in findings if f.severity is Severity.BLOCK),
        warn=sum(1 for f in findings if f.severity is Severity.WARN),
        note=sum(1 for f in findings if f.severity is Severity.NOTE),
    )


def clean_rate(checked: int, flagged: int) -> float | None:
    if checked < 0 or flagged < 0 or flagged > checked:
        raise ValueError(f"impossible counts: checked={checked}, flagged={flagged}")
    if checked == 0:
        return None
    return (checked - flagged) / checked


def assess_dimension(
    rubric: Rubric,
    label: str,
    *,
    checked: int,
    findings: Sequence[Finding],
    rendered: Sequence[ReportFinding],
    unjudged: int,
    unextracted: int = 0,
    cannot_tell: int = 0,
) -> DimensionResult:
    if len(findings) != len(rendered):
        raise ValueError("findings and rendered findings must align one to one")
    counts = severity_counts(findings)
    flagged = flagged_candidates(findings)
    if unjudged > 0 or unextracted > 0:
        status = DimensionStatus.INCOMPLETE
    elif checked == 0:
        status = DimensionStatus.NOT_APPLICABLE
    else:
        status = DimensionStatus.ASSESSED
    assessed = status is DimensionStatus.ASSESSED
    return DimensionResult(
        critic_id=rubric.id,
        label=label,
        invariant=rubric.invariant,
        status=status,
        checked=checked,
        flagged=flagged,
        clean_rate=clean_rate(checked, flagged) if assessed else None,
        floor_score=score_dimension(rubric, findings).score if assessed else None,
        blocked=counts.block > 0,
        counts=counts,
        unjudged=unjudged,
        unextracted=unextracted,
        cannot_tell=cannot_tell,
        findings=list(rendered),
    )
