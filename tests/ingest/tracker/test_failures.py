"""A tracker export missing a required column/field raises
UnrecognisedTrackerFormatError naming the offending file — never a silent
partial parse."""

from __future__ import annotations

import pytest

from probative.core.evidence import (
    CorruptSourceError,
    EmptySourceError,
    EvidenceKind,
    SourceFormat,
    Tier,
    UnrecognisedTrackerFormatError,
)
from probative.ingest.tracker import ingest_tracker
from tests.ingest.tracker._paths import FIXTURES


@pytest.mark.parametrize(
    ("filename", "fmt"),
    [
        ("jira_malformed_missing_status.csv", SourceFormat.JIRA_CSV),
        ("jira_malformed_missing_status.html", SourceFormat.JIRA_HTML),
        ("jira_malformed_missing_status.xml", SourceFormat.JIRA_XML),
        ("ado_malformed_missing_state.csv", SourceFormat.ADO_CSV),
        ("jira_no_table.html", SourceFormat.JIRA_HTML),
    ],
)
def test_missing_required_field_raises_named_error(filename: str, fmt: SourceFormat) -> None:
    path = FIXTURES / filename
    with pytest.raises(UnrecognisedTrackerFormatError) as exc_info:
        ingest_tracker(path, format=fmt, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    assert str(path) in str(exc_info.value)


def test_not_well_formed_xml_raises_corrupt_source_error() -> None:
    path = FIXTURES / "jira_not_well_formed.xml"
    with pytest.raises(CorruptSourceError) as exc_info:
        ingest_tracker(
            path, format=SourceFormat.JIRA_XML, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY
        )
    assert str(path) in str(exc_info.value)


@pytest.mark.parametrize(
    "fmt",
    [SourceFormat.JIRA_CSV, SourceFormat.JIRA_HTML, SourceFormat.JIRA_XML, SourceFormat.ADO_CSV],
)
def test_empty_file_raises_empty_source_error(tmp_path, fmt: SourceFormat) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "empty"
    path.write_bytes(b"")
    with pytest.raises(EmptySourceError) as exc_info:
        ingest_tracker(path, format=fmt, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    assert str(path) in str(exc_info.value)


def test_wrong_format_selector_raises_value_error() -> None:
    from probative.core.evidence import SourceFormat as SF

    with pytest.raises(ValueError, match="not a tracker format"):
        ingest_tracker(
            FIXTURES / "jira_visible.csv",
            format=SF.CSV,
            tier=Tier.T1,
            kind=EvidenceKind.DOCUMENTARY,
        )
