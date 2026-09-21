"""Markdown (.md, .markdown) extraction.

`text` is the verbatim normalised source — no HTML rendering, since offsets
must point at raw Markdown a human would read or quote. Heading tracking is
a hand-rolled line scanner rather than a new dependency: a fenced code block
(```/~~~) suppresses heading detection inside it, and a stack of (level,
text) tracks the current heading_path breadcrumb.
"""

from __future__ import annotations

import re
from pathlib import Path

from probative.core.evidence import Locator, LocatorRegion
from probative.ingest._extracted import ExtractedDocument
from probative.ingest._lines import decode_and_normalize_endings, split_keepends

NORMALIZATION_VERSION = "markdown/1"

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^(```+|~~~+)")


def extract(path: Path) -> ExtractedDocument:
    text = decode_and_normalize_endings(path)
    lines = split_keepends(text)

    regions: list[LocatorRegion] = []
    offset = 0
    in_fence = False
    fence_marker = ""
    stack: list[tuple[int, str]] = []

    for line in lines:
        start = offset
        end = offset + len(line)
        offset = end
        stripped = line.strip()

        fence_match = _FENCE.match(stripped)
        if fence_match:
            marker = fence_match.group(1)[0] * 3
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker or stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
        elif not in_fence:
            heading_match = _HEADING.match(stripped)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))

        heading_path = [title for _, title in stack] or None
        regions.append(
            LocatorRegion(
                start=start,
                end=end,
                locator=Locator(line=len(regions) + 1, heading_path=heading_path),
            )
        )

    return ExtractedDocument(
        text=text, locator_regions=regions, normalization_version=NORMALIZATION_VERSION
    )
