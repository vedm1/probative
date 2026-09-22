"""jira_html.py against a real 'Export current fields to HTML' shape —
lozenge-wrapped status, anchor-wrapped key, wiki markup with <br/> for
newlines (confirmed against a real export; see generate.py)."""

from __future__ import annotations

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.ingest.tracker import ingest_tracker, issues
from tests.ingest.tracker._paths import FIXTURES


def _issues_by_key() -> dict[str, object]:
    source = ingest_tracker(
        FIXTURES / "jira_issues.html",
        format=SourceFormat.JIRA_HTML,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    return {i.key: i for i in issues(source)}


def test_status_and_key_extracted_despite_nested_markup() -> None:
    by_key = _issues_by_key()
    demo1 = by_key["DEMO-1"]
    assert demo1.key == "DEMO-1"
    assert demo1.status == "Open"
    assert demo1.type == "Bug"


def test_hierarchy_and_acceptance_criteria_recognised() -> None:
    by_key = _issues_by_key()
    demo2 = by_key["DEMO-2"]
    assert demo2.parent_key == "DEMO-1"
    assert demo2.acceptance_criteria is not None
    assert "reset link is emailed" in demo2.acceptance_criteria.text

    demo3 = by_key["DEMO-3"]
    assert demo3.parent_key is None
    assert demo3.description is None


def test_description_normalises_the_same_as_the_csv_equivalent() -> None:
    """Same wiki-markup content as jira_csv's DEMO-1, wrapped in <br/>
    instead of literal newlines — both must normalise identically."""
    by_key = _issues_by_key()
    text = by_key["DEMO-1"].description.text
    assert "Click the login button" in text
    assert "important note" in text
    assert "*important*" not in text
    assert "[~accountid:" not in text
