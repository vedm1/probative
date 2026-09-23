"""One failure case per way a declared Confluence export can fail to match
its declared format — never silently degraded."""

from __future__ import annotations

import pytest

from probative.core.evidence import (
    CorruptSourceError,
    EmptySourceError,
    EvidenceKind,
    SourceFormat,
    Tier,
)
from probative.ingest.confluence import ingest_confluence
from tests.ingest.confluence._paths import FIXTURES


def _ingest(filename: str):  # type: ignore[no-untyped-def]
    return ingest_confluence(
        FIXTURES / filename,
        format=SourceFormat.CONFLUENCE_WORD,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )


def test_empty_file_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    empty = tmp_path / "empty.doc"
    empty.write_bytes(b"")
    with pytest.raises(EmptySourceError):
        ingest_confluence(
            empty, format=SourceFormat.CONFLUENCE_WORD, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY
        )


def test_not_a_mime_message_is_rejected() -> None:
    with pytest.raises(CorruptSourceError, match="no text/html part"):
        _ingest("not_mime.doc")


def test_mime_message_with_no_html_part_is_rejected() -> None:
    with pytest.raises(CorruptSourceError, match="no text/html part"):
        _ingest("mime_no_html_part.doc")


def test_empty_body_is_rejected() -> None:
    with pytest.raises(EmptySourceError):
        _ingest("empty_body.doc")


def test_missing_body_tag_is_rejected() -> None:
    with pytest.raises(CorruptSourceError, match="no <body>"):
        _ingest("no_body.doc")


def test_bad_encoding_is_rejected() -> None:
    with pytest.raises(CorruptSourceError, match="not valid"):
        _ingest("mime_bad_encoding.doc")


def test_unrecognised_format_raises_value_error() -> None:
    with pytest.raises(ValueError, match="not a Confluence format"):
        ingest_confluence(
            FIXTURES / "page_export.doc",
            format=SourceFormat.JIRA_CSV,
            tier=Tier.T1,
            kind=EvidenceKind.DOCUMENTARY,
        )
