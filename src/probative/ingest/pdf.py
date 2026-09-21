"""PDF (.pdf, text-layer only) extraction.

Uses pdfplumber (wraps pdfminer.six, both MIT) rather than PyMuPDF, which is
AGPL-licensed and would taint an Apache-2.0-distributed dependency tree.

If any page has no extractable text (an image-only/scanned page), the whole
document is refused with NoTextLayerError — not just that page. A document
that is mostly real text and partly a scanned exhibit should not quietly
lose the exhibit; this mirrors the project's "no silent partial extraction"
posture generally, not only for OCR.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from probative.core.evidence import (
    CorruptSourceError,
    EncryptedSourceError,
    Locator,
    LocatorRegion,
    NoTextLayerError,
)
from probative.ingest._extracted import ExtractedDocument

NORMALIZATION_VERSION = "pdf/1"


def extract(path: Path) -> ExtractedDocument:
    try:
        pdf = pdfplumber.open(path)
    except PdfminerException as exc:
        # pdfplumber wraps every pdfminer parse failure into its own
        # PdfminerException, discarding the original type but keeping it
        # as __context__ — that's the only way to tell "wrong password"
        # apart from "not a valid PDF" here.
        if isinstance(exc.__context__, PDFPasswordIncorrect):
            raise EncryptedSourceError(path, f"password-protected: {exc}") from exc
        raise CorruptSourceError(path, f"not a valid PDF: {exc}") from exc

    with pdf:
        blank_pages = [i for i, page in enumerate(pdf.pages, start=1) if not page.chars]
        if blank_pages:
            raise NoTextLayerError(
                path,
                f"no extractable text on page(s) {blank_pages} — scanned/image-only "
                f"content needs OCR, which PB1 refuses rather than silently skipping",
            )

        text_parts: list[str] = []
        regions: list[LocatorRegion] = []
        offset = 0
        for page_num, page in enumerate(pdf.pages, start=1):
            extracted = page.extract_text() or ""
            lines = extracted.splitlines()
            for line_num, line_text in enumerate(lines, start=1):
                line = line_text + "\n"
                start = offset
                end = offset + len(line)
                offset = end
                text_parts.append(line)
                regions.append(
                    LocatorRegion(
                        start=start, end=end, locator=Locator(page=page_num, line=line_num)
                    )
                )

    return ExtractedDocument(
        text="".join(text_parts),
        locator_regions=regions,
        normalization_version=NORMALIZATION_VERSION,
    )
