"""reextract_confluence's failure modes — same guarantees as PB1's
reextract() / PB2's reextract_tracker(), applied to Confluence Sources."""

from __future__ import annotations

import pytest

from probative.core.evidence import (
    CorruptSourceError,
    EvidenceKind,
    SourceFormat,
    StaleNormalizationError,
    Tier,
)
from probative.ingest import spans
from probative.ingest.confluence import ingest_confluence, reextract_confluence
from tests.ingest.confluence._paths import FIXTURES


def _source():  # type: ignore[no-untyped-def]
    return ingest_confluence(
        FIXTURES / "page_export.doc",
        format=SourceFormat.CONFLUENCE_WORD,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )


def test_rejects_a_span_from_a_different_source() -> None:
    source = _source()
    other = _source().model_copy(update={"id": "src_not_this_one"})
    (span,) = spans(other, [(other.locator_regions[0].start, other.locator_regions[0].end)])

    with pytest.raises(ValueError, match="belongs to source"):
        reextract_confluence(source, span)


def test_rejects_a_stale_normalization_version() -> None:
    source = _source()
    (span,) = spans(source, [(source.locator_regions[0].start, source.locator_regions[0].end)])
    stale = source.model_copy(update={"extractor_version": "confluence_word/0-does-not-exist"})

    with pytest.raises(StaleNormalizationError):
        reextract_confluence(stale, span)


def test_rejects_a_file_that_changed_on_disk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "page_export.doc"
    path.write_bytes((FIXTURES / "page_export.doc").read_bytes())
    source = ingest_confluence(
        path, format=SourceFormat.CONFLUENCE_WORD, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY
    )
    (span,) = spans(source, [(source.locator_regions[0].start, source.locator_regions[0].end)])

    path.write_bytes(path.read_bytes() + b"\r\n")

    with pytest.raises(CorruptSourceError):
        reextract_confluence(source, span)
