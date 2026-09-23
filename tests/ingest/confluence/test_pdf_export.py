"""Confluence's "Export to PDF" needs no new extractor: it is a well-formed
PDF, ingested through PB1's existing `probative.ingest.ingest()` /
`SourceFormat.PDF` unchanged.

This characterises a real, confirmed finding rather than testing new code:
the export is a print of the whole browser page, so `pdf.py`'s
`page.extract_text()` faithfully captures the top navigation chrome as
literal text ahead of the actual page content. That is not a parsing bug —
it is genuinely on the page — so PB2-p2 does not attempt to strip it; this
test locks the behaviour in so a future change to `pdf.py` doesn't silently
alter it.
"""

from __future__ import annotations

from probative.core.evidence import EvidenceKind, Tier
from probative.ingest import ingest
from tests.ingest.confluence._paths import FIXTURES


def test_pdf_export_carries_navigation_chrome_ahead_of_page_content() -> None:
    source = ingest(FIXTURES / "page.pdf", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)

    chrome_index = source.text.find("Home")
    title_index = source.text.find("Widget classification based on availability")
    content_index = source.text.find("Sprocket")

    assert chrome_index != -1
    assert title_index != -1
    assert content_index != -1
    assert chrome_index < title_index < content_index
