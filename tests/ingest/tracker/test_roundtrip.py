"""Every tracker EvidenceSpan's offsets must survive re-extraction —
the phase's reason to exist, same as PB1's test_roundtrip.py."""

from __future__ import annotations

import pytest

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.ingest.tracker import ingest_tracker, issues, reextract_tracker
from tests.ingest.tracker._paths import FIXTURES

HAPPY_PATH_FIXTURES = [
    ("jira_visible.csv", SourceFormat.JIRA_CSV),
    ("jira_all_fields.csv", SourceFormat.JIRA_CSV),
    ("jira_issues.html", SourceFormat.JIRA_HTML),
    ("jira_export.xml", SourceFormat.JIRA_XML),
    ("ado_issues.csv", SourceFormat.ADO_CSV),
    ("ado_with_acceptance_criteria.csv", SourceFormat.ADO_CSV),
]


@pytest.mark.parametrize(("filename", "fmt"), HAPPY_PATH_FIXTURES)
def test_every_issue_field_span_reextracts_exactly(filename: str, fmt: SourceFormat) -> None:
    source = ingest_tracker(
        FIXTURES / filename, format=fmt, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY
    )
    for issue in issues(source):
        assert reextract_tracker(source, issue.summary) == issue.summary.text
        for span in (issue.description, issue.acceptance_criteria):
            if span is not None:
                assert reextract_tracker(source, span) == span.text


def test_every_optional_field_kind_is_exercised_by_some_fixture() -> None:
    """Guards against the parametrised test above silently covering only
    the required `summary` field on every fixture."""
    saw_description = False
    saw_acceptance_criteria = False
    for filename, fmt in HAPPY_PATH_FIXTURES:
        source = ingest_tracker(
            FIXTURES / filename, format=fmt, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY
        )
        for issue in issues(source):
            saw_description = saw_description or issue.description is not None
            saw_acceptance_criteria = (
                saw_acceptance_criteria or issue.acceptance_criteria is not None
            )
    assert saw_description
    assert saw_acceptance_criteria


@pytest.mark.parametrize(("filename", "fmt"), HAPPY_PATH_FIXTURES)
def test_reingesting_the_same_file_is_idempotent(filename: str, fmt: SourceFormat) -> None:
    path = FIXTURES / filename
    first = ingest_tracker(path, format=fmt, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    second = ingest_tracker(path, format=fmt, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    assert first.id == second.id
    assert first.sha256 == second.sha256
    assert first.text == second.text
    assert first.locator_regions == second.locator_regions
