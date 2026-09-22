"""jira_csv.py against both real column-set shapes: the small 'visible
fields' export and the 234-column 'all fields' export (confirmed against
real Jira exports during the PB2 build session — see generate.py)."""

from __future__ import annotations

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.ingest.tracker import ingest_tracker, issues
from tests.ingest.tracker._paths import FIXTURES


def _issues_by_key(filename: str) -> dict[str, object]:
    source = ingest_tracker(
        FIXTURES / filename,
        format=SourceFormat.JIRA_CSV,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    return {i.key: i for i in issues(source)}


def test_visible_fields_export_recognises_core_fields_only() -> None:
    by_key = _issues_by_key("jira_visible.csv")
    assert set(by_key) == {"DEMO-1", "DEMO-2", "DEMO-3", "DEMO-4"}
    demo1 = by_key["DEMO-1"]
    assert demo1.type == "Bug"
    assert demo1.status == "Open"
    assert demo1.summary.text == "Login button is unresponsive"
    # None of these columns exist in a real "visible fields" export.
    assert demo1.parent_key is None
    assert demo1.description is None
    assert demo1.acceptance_criteria is None


def test_all_fields_export_is_column_order_and_repeat_column_independent() -> None:
    by_key = _issues_by_key("jira_all_fields.csv")
    assert set(by_key) == {"DEMO-1", "DEMO-2", "DEMO-3", "DEMO-4"}

    demo2 = by_key["DEMO-2"]
    assert demo2.type == "Story"
    assert demo2.parent_key == "DEMO-1"
    assert demo2.acceptance_criteria is not None
    assert "reset link is emailed" in demo2.acceptance_criteria.text

    demo3 = by_key["DEMO-3"]
    assert demo3.description is None
    assert demo3.acceptance_criteria is None


def test_wiki_markup_description_is_normalised() -> None:
    by_key = _issues_by_key("jira_all_fields.csv")
    text = by_key["DEMO-1"].description.text
    assert "# Click" not in text
    assert "*important*" not in text
    assert "[~accountid:abc123]" not in text
    assert "[tracking issue|" not in text
    assert "!screenshot.png!" not in text
    assert "Click the login button" in text
    assert "important note" in text
    assert "tracking issue" in text


def test_evidence_span_offsets_resolve_into_source_text() -> None:
    source = ingest_tracker(
        FIXTURES / "jira_all_fields.csv",
        format=SourceFormat.JIRA_CSV,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    demo2 = {i.key: i for i in issues(source)}["DEMO-2"]
    span = demo2.summary
    assert source.text[span.start : span.end] == span.text == "Add password reset flow"
