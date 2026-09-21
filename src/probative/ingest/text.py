"""Plain text (.txt) extraction."""

from __future__ import annotations

from pathlib import Path

from probative.core.evidence import Locator
from probative.ingest._extracted import ExtractedDocument
from probative.ingest._lines import decode_and_normalize_endings, line_regions, split_keepends

NORMALIZATION_VERSION = "text/1"


def extract(path: Path) -> ExtractedDocument:
    text = decode_and_normalize_endings(path)
    lines = split_keepends(text)
    regions = line_regions(lines, lambda i, _line: Locator(line=i))
    return ExtractedDocument(
        text=text, locator_regions=regions, normalization_version=NORMALIZATION_VERSION
    )
