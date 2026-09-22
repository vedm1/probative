"""ado_csv.py: HTML Description normalisation, and the dangling-parent
case confirmed against a real export (0 of 17 distinct parents resolved
within a real 40-row sample)."""

from __future__ import annotations

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.ingest.tracker import ingest_tracker, issues
from tests.ingest.tracker._paths import FIXTURES


def test_html_description_is_normalised() -> None:
    source = ingest_tracker(
        FIXTURES / "ado_issues.csv",
        format=SourceFormat.ADO_CSV,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    by_key = {i.key: i for i in issues(source)}
    text = by_key["30002"].description.text
    assert "<div>" not in text
    assert "&nbsp;" not in text
    assert "As a user" in text
    assert "I need to reset my password" in text


def test_dangling_parent_recorded_verbatim_without_error() -> None:
    source = ingest_tracker(
        FIXTURES / "ado_issues.csv",
        format=SourceFormat.ADO_CSV,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    by_key = {i.key: i for i in issues(source)}
    # "99999" does not appear as an ID anywhere in this export.
    assert by_key["30002"].parent_key == "99999"
    assert {i.key for i in issues(source)} == {"30001", "30002", "30003"}
    assert by_key["30003"].parent_key == "30002"


def test_acceptance_criteria_recognised_when_column_present() -> None:
    source = ingest_tracker(
        FIXTURES / "ado_with_acceptance_criteria.csv",
        format=SourceFormat.ADO_CSV,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    (issue,) = issues(source)
    assert issue.acceptance_criteria is not None
    assert "reset email is sent" in issue.acceptance_criteria.text


def test_acceptance_criteria_absent_when_no_column() -> None:
    source = ingest_tracker(
        FIXTURES / "ado_issues.csv",
        format=SourceFormat.ADO_CSV,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    for issue in issues(source):
        assert issue.acceptance_criteria is None
