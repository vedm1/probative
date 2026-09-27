from __future__ import annotations

from probative.core.critic import Finding, Rubric, RubricCheck, Severity
from probative.critics.scoring import aggregate, score_dimension


def _rubric(rubric_id: str, severity: Severity = Severity.WARN) -> Rubric:
    return Rubric(
        id=rubric_id,
        severity=severity,
        checks=[RubricCheck(id="c", description="d", remedy="r")],
        clean_fixtures="x",
        defect_fixtures="y",
    )


def _finding(critic_id: str, severity: Severity, check_id: str = "c") -> Finding:
    return Finding(
        critic_id=critic_id,
        check_id=check_id,
        severity=severity,
        invariant=None,
        message="m",
        remedy="r",
    )


def test_score_dimension_no_findings_is_ceiling() -> None:
    rubric = _rubric("r1")
    result = score_dimension(rubric, [])
    assert result.score == 10.0
    assert result.blocked is False
    assert result.findings == []


def test_score_dimension_block_finding_zeroes_score() -> None:
    rubric = _rubric("r1")
    findings = [
        _finding("r1", Severity.WARN),
        _finding("r1", Severity.BLOCK),
        _finding("r1", Severity.NOTE),
    ]
    result = score_dimension(rubric, findings)
    assert result.score == 0.0
    assert result.blocked is True


def test_score_dimension_warn_findings_deduct_two_each() -> None:
    rubric = _rubric("r1")
    findings = [_finding("r1", Severity.WARN), _finding("r1", Severity.WARN)]
    result = score_dimension(rubric, findings)
    assert result.score == 6.0
    assert result.blocked is False


def test_score_dimension_note_findings_deduct_half_each() -> None:
    rubric = _rubric("r1")
    findings = [_finding("r1", Severity.NOTE) for _ in range(3)]
    result = score_dimension(rubric, findings)
    assert result.score == 8.5


def test_score_dimension_floors_at_zero() -> None:
    rubric = _rubric("r1")
    findings = [_finding("r1", Severity.WARN) for _ in range(10)]
    result = score_dimension(rubric, findings)
    assert result.score == 0.0
    assert result.blocked is False


def test_score_dimension_ignores_other_critics_findings() -> None:
    rubric = _rubric("r1")
    findings = [_finding("other_critic", Severity.BLOCK)]
    result = score_dimension(rubric, findings)
    assert result.score == 10.0
    assert result.blocked is False
    assert result.findings == []


def test_score_dimension_is_deterministic() -> None:
    rubric = _rubric("r1")
    findings = [_finding("r1", Severity.WARN)]
    assert score_dimension(rubric, findings) == score_dimension(rubric, findings)


def test_aggregate_returns_one_score_per_rubric_in_order() -> None:
    r1 = _rubric("r1")
    r2 = _rubric("r2")
    findings = [_finding("r1", Severity.WARN), _finding("r2", Severity.BLOCK)]

    results = aggregate([r1, r2], findings)

    assert [r.critic_id for r in results] == ["r1", "r2"]
    assert results[0].score == 8.0
    assert results[1].blocked is True
