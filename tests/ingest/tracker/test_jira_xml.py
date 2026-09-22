"""jira_xml.py against a real RSS/XML export shape: escaped real HTML
descriptions (a different normalisation path than the wiki markup in
jira_csv/jira_html), and <parent id="..."> for hierarchy."""

from __future__ import annotations

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.ingest.tracker import ingest_tracker, issues
from tests.ingest.tracker._paths import FIXTURES


def _issues_by_key() -> dict[str, object]:
    source = ingest_tracker(
        FIXTURES / "jira_export.xml",
        format=SourceFormat.JIRA_XML,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    return {i.key: i for i in issues(source)}


def test_html_description_normalises_to_plain_text() -> None:
    by_key = _issues_by_key()
    text = by_key["DEMO-1"].description.text
    assert "<p>" not in text
    assert "<ol>" not in text
    assert "<li>" not in text
    assert "Click the login button" in text
    assert "Observe that nothing happens" in text


def test_parent_hierarchy_from_parent_element() -> None:
    by_key = _issues_by_key()
    assert by_key["DEMO-1"].parent_key is None
    assert by_key["DEMO-2"].parent_key == "DEMO-1"
    assert by_key["DEMO-4"].parent_key == "DEMO-2"


def test_acceptance_criteria_from_customfields() -> None:
    by_key = _issues_by_key()
    ac = by_key["DEMO-2"].acceptance_criteria
    assert ac is not None
    assert "reset link is emailed" in ac.text
    assert by_key["DEMO-3"].acceptance_criteria is None
