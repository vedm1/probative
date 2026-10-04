"""Quote -> `EvidenceSpan` resolution.

The model's quote is only a search key. The span's text is always sliced
from `source.text`, so what is recorded is what the document says, never the
model's rendering of it (I1). There is no fuzzy matching beyond whitespace,
and that is bounded: a quote's tokens may be separated by spaces or a single
line break (a PDF wrap), never by a blank line, so a quote cannot stitch two
statements or a heading into one span. A paraphrase is not a quote and is
rejected.
"""

from __future__ import annotations

import re

from probative.core.candidates import RejectReason
from probative.core.evidence import EvidenceSpan, Source
from probative.ingest import spans

# Spaces/tabs, or exactly one line break with optional indentation — never \n\n.
_GAP = r"(?:[^\S\n]+|[^\S\n]*\n[^\S\n]*)"


def _on_word_boundaries(text: str, start: int, end: int) -> bool:
    """A quote that begins or ends mid-word is a substring, not a quotation."""
    if start > 0 and text[start].isalnum() and text[start - 1].isalnum():
        return False
    return not (end < len(text) and text[end - 1].isalnum() and text[end].isalnum())


def _exact(text: str, quote: str, window: tuple[int, int]) -> list[tuple[int, int]]:
    lo, hi = window
    found: list[tuple[int, int]] = []
    pos = lo
    while (idx := text.find(quote, pos, hi)) != -1:
        found.append((idx, idx + len(quote)))
        pos = idx + 1
    return found


def occurrences(
    text: str, quote: str, window: tuple[int, int], *, loose_only: bool = False
) -> list[tuple[int, int]]:
    """Where `quote` occurs in `text[window]`, on word boundaries: exact
    matches, else (or only, when `loose_only`) whitespace-tolerant ones."""
    lo, hi = window
    if not loose_only:
        exact = [m for m in _exact(text, quote, window) if _on_word_boundaries(text, *m)]
        if exact:
            return exact
    pattern = re.compile(_GAP.join(re.escape(token) for token in quote.split()))
    return [
        (m.start(), m.end())
        for m in pattern.finditer(text, lo, hi)
        if _on_word_boundaries(text, m.start(), m.end())
    ]


def resolve_quote(
    source: Source,
    quote: str,
    *,
    window: tuple[int, int],
    claimed: set[tuple[int, int]],
    max_quote_chars: int,
) -> EvidenceSpan | RejectReason:
    """Locate `quote` in `source.text[window]`, or say why it cannot be.

    `claimed` holds the `(start, end)` ranges already taken by this kind; a
    repeated quote takes the next unclaimed occurrence. `max_quote_chars`
    bounds the *matched* span, not just the model's string.
    """
    stripped = quote.strip()
    if not any(ch.isalnum() for ch in stripped):
        return RejectReason.EMPTY
    matches = occurrences(source.text, stripped, window)
    if not matches:
        return RejectReason.NOT_FOUND
    in_budget = [m for m in matches if m[1] - m[0] <= max_quote_chars]
    if not in_budget:
        return RejectReason.TOO_LONG
    for start, end in in_budget:
        if (start, end) not in claimed:
            return spans(source, [(start, end)])[0]
    return RejectReason.DUPLICATE
