"""Shared line-splitting helper for the line-oriented formats (text, CSV,
Markdown): decode, normalise line endings, and build one LocatorRegion per
physical line without losing any characters (offsets must stay exact)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from probative.core.evidence import CorruptSourceError, Locator, LocatorRegion


def decode_and_normalize_endings(path: Path) -> str:
    """Decode UTF-8 (tolerating a leading BOM) and normalise CRLF/CR to LF."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CorruptSourceError(path, f"not valid UTF-8: {exc}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_keepends(text: str) -> list[str]:
    """Split into physical lines, each carrying its own trailing "\\n"
    (the last line may lack one) — so ''.join(lines) == text exactly."""
    return text.splitlines(keepends=True)


def line_regions(
    lines: list[str], locator_for_line: Callable[[int, str], Locator]
) -> list[LocatorRegion]:
    """Build one LocatorRegion per line in `lines`, given a callable
    `locator_for_line(1_indexed_line_number, line_text) -> Locator`."""
    regions: list[LocatorRegion] = []
    offset = 0
    for i, line in enumerate(lines, start=1):
        start = offset
        end = offset + len(line)
        regions.append(LocatorRegion(start=start, end=end, locator=locator_for_line(i, line)))
        offset = end
    return regions
