"""Every Confluence-export EvidenceSpan's offsets must survive
re-extraction — the phase's reason to exist, same as PB1/PB2's own
test_roundtrip.py."""

from __future__ import annotations

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.ingest import spans
from probative.ingest.confluence import ingest_confluence, reextract_confluence
from tests.ingest.confluence._paths import FIXTURES


def test_every_region_span_reextracts_exactly() -> None:
    source = ingest_confluence(
        FIXTURES / "page_export.doc",
        format=SourceFormat.CONFLUENCE_WORD,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    ranges = [(r.start, r.end) for r in source.locator_regions if r.start < r.end]
    for span in spans(source, ranges):
        assert reextract_confluence(source, span) == span.text


def test_reingesting_the_same_file_is_idempotent() -> None:
    path = FIXTURES / "page_export.doc"
    first = ingest_confluence(
        path, format=SourceFormat.CONFLUENCE_WORD, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY
    )
    second = ingest_confluence(
        path, format=SourceFormat.CONFLUENCE_WORD, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY
    )
    assert first.id == second.id
    assert first.sha256 == second.sha256
    assert first.text == second.text
    assert first.locator_regions == second.locator_regions
