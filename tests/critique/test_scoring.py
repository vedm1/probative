from __future__ import annotations

import pytest

from probative.core.critic import Finding, Rubric, RubricCheck, Severity
from probative.critics.scoring import score_dimension
from probative.critique.report import DimensionStatus, report_finding
from probative.critique.scoring import assess_dimension, clean_rate, flagged_candidates
from tests.critique._builders import make_finding, make_source, span_of

SOURCE = make_source("Users need a button. Users need a dashboard. Users need an export.\n")


def _rubric() -> Rubric:
    return Rubric(
        id="space_warden",
        severity=Severity.BLOCK,
        invariant="I3",
        checks=[RubricCheck(id="names_feature", description="d", remedy="r")],
        clean_fixtures="x",
        defect_fixtures="y",
    )


def _f(phrase: str, severity: Severity, target: str, check: str = "names_feature") -> Finding:
    return make_finding(
        severity=severity,
        target_id=target,
        check_id=check,
        evidence=span_of(SOURCE, phrase),
    )


def _assess(findings: list[Finding], checked: int, unjudged: int = 0):  # type: ignore[no-untyped-def]
    rendered = [report_finding(f, SOURCE) for f in findings]
    return assess_dimension(
        _rubric(),
        "Problem framing",
        checked=checked,
        findings=findings,
        rendered=rendered,
        unjudged=unjudged,
    )


def test_nothing_checked_is_not_applicable_never_clean() -> None:
    result = _assess([], checked=0)
    assert result.status is DimensionStatus.NOT_APPLICABLE
    assert result.clean_rate is None and result.floor_score is None
    assert result.blocked is False


def test_all_clean_is_assessed_with_full_rate() -> None:
    result = _assess([], checked=4)
    assert result.status is DimensionStatus.ASSESSED
    assert (result.checked, result.flagged, result.clean) == (4, 0, 4)
    assert result.clean_rate == 1.0 and result.floor_score == 10.0


def test_three_findings_on_one_candidate_flag_it_once() -> None:
    findings = [
        _f("button", Severity.WARN, "c1", "a"),
        _f("dashboard", Severity.WARN, "c1", "b"),
        _f("export", Severity.BLOCK, "c1", "c"),
    ]
    result = _assess(findings, checked=4)
    assert result.flagged == 1 and result.clean == 3 and result.clean_rate == 0.75


def test_notes_do_not_flag() -> None:
    result = _assess([_f("button", Severity.NOTE, "c1")], checked=2)
    assert result.flagged == 0 and result.clean_rate == 1.0
    assert result.counts.note == 1


def test_block_sets_blocked_and_floor_zero() -> None:
    result = _assess([_f("button", Severity.BLOCK, "c1")], checked=2)
    assert result.blocked is True and result.floor_score == 0.0
    assert result.counts.block == 1 and result.clean_rate == 0.5


def test_floor_matches_pb3_score_dimension() -> None:
    findings = [_f("button", Severity.WARN, "c1"), _f("export", Severity.NOTE, "c2")]
    result = _assess(findings, checked=5)
    assert result.floor_score == score_dimension(_rubric(), findings).score


def test_oi18_same_floor_different_rate_by_candidate_count() -> None:
    warns = [_f("button", Severity.WARN, f"c{i}") for i in range(5)]
    small = _assess(warns, checked=5)
    large = _assess(warns, checked=500)
    assert small.floor_score == large.floor_score == 0.0
    assert small.blocked is False and large.blocked is False
    assert small.clean_rate == 0.0 and large.clean_rate == pytest.approx(0.99)


def test_unjudged_makes_the_dimension_incomplete_with_no_rate() -> None:
    result = _assess([_f("button", Severity.BLOCK, "c1")], checked=6, unjudged=3)
    assert result.status is DimensionStatus.INCOMPLETE
    assert result.clean_rate is None and result.floor_score is None
    assert result.unjudged == 3 and result.blocked is True


def test_findings_and_rendered_must_align() -> None:
    with pytest.raises(ValueError):
        assess_dimension(
            _rubric(),
            "x",
            checked=1,
            findings=[],
            rendered=[report_finding(_f("button", Severity.WARN, "c1"), SOURCE)],
            unjudged=0,
        )


@pytest.mark.parametrize("checked,flagged", [(1, 0), (7, 3), (12, 12)])
def test_clean_plus_flagged_is_checked(checked: int, flagged: int) -> None:
    rate = clean_rate(checked, flagged)
    assert rate == (checked - flagged) / checked


def test_clean_rate_rejects_impossible_inputs() -> None:
    assert clean_rate(0, 0) is None
    with pytest.raises(ValueError):
        clean_rate(2, 3)


def test_flagged_candidates_counts_distinct_block_and_warn_targets() -> None:
    findings = [
        _f("button", Severity.WARN, "c1"),
        _f("button", Severity.BLOCK, "c1", "x"),
        _f("export", Severity.NOTE, "c2"),
        _f("dashboard", Severity.WARN, "c3"),
    ]
    assert flagged_candidates(findings) == 2
