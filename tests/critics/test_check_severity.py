"""PB5: an optional per-check severity, so a rubric can say INVEST blocks only
on `testable` without the policy hiding in critic code (S2: rubrics are data)."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from probative.core.critic import Finding, Rubric, RubricCheck, Severity
from probative.critics.base import Critic


class _NoOp(Critic):
    def check(self, candidates: Sequence[BaseModel]) -> list[Finding]:
        return []


def _critic(rubric_severity: Severity, check_severity: Severity | None) -> _NoOp:
    rubric = Rubric(
        id="r",
        severity=rubric_severity,
        checks=[RubricCheck(id="c", description="d", remedy="fix", severity=check_severity)],
        clean_fixtures="c/*.json",
        defect_fixtures="d/*.json",
    )
    return _NoOp(rubric)


def test_check_severity_defaults_to_none() -> None:
    assert RubricCheck(id="c", description="d", remedy="r").severity is None


def test_unset_check_severity_falls_through_to_the_rubric() -> None:
    finding = _critic(Severity.WARN, None)._finding(check_id="c", message="m")
    assert finding.severity == Severity.WARN


def test_check_severity_overrides_the_rubric() -> None:
    finding = _critic(Severity.WARN, Severity.BLOCK)._finding(check_id="c", message="m")
    assert finding.severity == Severity.BLOCK


def test_explicit_argument_beats_the_check_and_the_rubric() -> None:
    finding = _critic(Severity.WARN, Severity.BLOCK)._finding(
        check_id="c", message="m", severity=Severity.NOTE
    )
    assert finding.severity == Severity.NOTE
