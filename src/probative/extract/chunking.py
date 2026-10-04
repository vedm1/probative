"""Split a `Source` into contiguous character windows for per-call limits.

Windows never overlap and always cover `[0, len(text))`. A quote that
straddles two windows cannot be resolved in either — an accepted, rare loss
that is preferable to duplicating text across calls.
"""

from __future__ import annotations

from probative.core.evidence import Source


def _split_oversize(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    pieces: list[tuple[int, int]] = []
    while end - start > max_chars:
        limit = start + max_chars
        idx = text.rfind("\n\n", start + 1, limit)
        if idx > start:
            cut = idx + 2
        else:
            idx = text.rfind("\n", start + 1, limit)
            cut = idx + 1 if idx > start else limit
        pieces.append((start, cut))
        start = cut
    pieces.append((start, end))
    return pieces


def chunk_windows(source: Source, *, max_chars: int) -> list[tuple[int, int]]:
    if max_chars < 1:
        raise ValueError(f"max_chars must be at least 1, got {max_chars}")
    text = source.text
    if len(text) <= max_chars:
        return [(0, len(text))]
    pieces: list[tuple[int, int]] = []
    for region in source.locator_regions:
        if region.end - region.start <= max_chars:
            pieces.append((region.start, region.end))
        else:
            pieces.extend(_split_oversize(text, region.start, region.end, max_chars))
    windows: list[tuple[int, int]] = []
    for start, end in pieces:
        if windows and end - windows[-1][0] <= max_chars:
            windows[-1] = (windows[-1][0], end)
        else:
            windows.append((start, end))
    return windows
