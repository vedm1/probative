"""Locator correctness: a span reports the human-meaningful place a
practitioner would actually look — the PDF page, the XLSX sheet+cell, the
Markdown heading breadcrumb."""

from __future__ import annotations

from probative.core.evidence import EvidenceKind, Tier
from probative.ingest import ingest, spans
from tests.ingest._paths import FIXTURES


def test_pdf_span_reports_correct_page() -> None:
    source = ingest(FIXTURES / "memo.pdf", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    page_two_offset = source.text.index("Page two")
    (span,) = spans(source, [(page_two_offset, page_two_offset + 8)])
    assert span.locator.page == 2


def test_xlsx_span_reports_correct_sheet_and_cell() -> None:
    source = ingest(FIXTURES / "sheet.xlsx", tier=Tier.T1, kind=EvidenceKind.SYSTEM)
    platform_offset = source.text.index("Platform")
    (span,) = spans(source, [(platform_offset, platform_offset + len("Platform"))])
    assert span.locator.sheet == "People"
    assert span.locator.cell == "B7"


def test_markdown_span_under_nested_heading_reports_full_path() -> None:
    source = ingest(FIXTURES / "notes.md", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    scope_body_offset = source.text.index("The scope is deliberately narrow")
    (span,) = spans(source, [(scope_body_offset, scope_body_offset + 10)])
    assert span.locator.heading_path == ["Introduction", "Scope"]


def test_markdown_heading_marker_inside_fence_is_not_a_heading() -> None:
    source = ingest(FIXTURES / "notes.md", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    fenced_offset = source.text.index("this is not a heading")
    (span,) = spans(source, [(fenced_offset, fenced_offset + 10)])
    # Still under "Scope" — the `#` inside the fence did not open a new
    # top-level heading and reset the breadcrumb.
    assert span.locator.heading_path == ["Introduction", "Scope"]
