"""CSV (.csv) extraction.

Cell-agnostic: `text` is the verbatim normalised source, one LocatorRegion
per physical line. Out of scope: a quoted field containing a literal
newline (one CSV record spanning multiple physical lines) is not handled —
each physical line is assumed to be exactly one record.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from probative.core.evidence import Locator, MalformedCSVError
from probative.ingest._extracted import ExtractedDocument
from probative.ingest._lines import decode_and_normalize_endings, line_regions, split_keepends

NORMALIZATION_VERSION = "csv/1"


def _column_count(line: str) -> int | None:
    stripped = line.strip("\n")
    if stripped == "":
        return None
    row = next(csv.reader(io.StringIO(stripped)))
    return len(row)


def extract(path: Path) -> ExtractedDocument:
    text = decode_and_normalize_endings(path)
    lines = split_keepends(text)

    expected_columns: int | None = None
    for i, line in enumerate(lines, start=1):
        count = _column_count(line)
        if count is None:
            continue
        if expected_columns is None:
            expected_columns = count
        elif count != expected_columns:
            raise MalformedCSVError(
                path,
                f"line {i} has {count} column(s), expected {expected_columns} (from the header)",
            )

    regions = line_regions(lines, lambda i, _line: Locator(line=i))
    return ExtractedDocument(
        text=text, locator_regions=regions, normalization_version=NORMALIZATION_VERSION
    )
