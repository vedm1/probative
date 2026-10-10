"""Place a verified quote on a line of the PR's file, or decline (PB35, I1).

`source.text` is the *normalised* file (BOM dropped, line endings turned into LF), and
the Markdown `Locator.line` counts regions rather than file lines, so neither offsets nor
locators are used. The quote is searched in the normalised fetched text instead. Anything
short of a unique match on a line the PR added is a summary entry with a reason: the
action may downgrade a finding, never invent a location.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from probative.interfaces.github.patch import PatchMap

Reason = Literal[
    "ambiguous_quote", "quote_not_found", "unchanged_text", "no_patch", "not_line_addressable"
]


class Anchor(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["inline", "summary"]
    start_line: int | None = None
    end_line: int | None = None
    reason: Reason | None = None


def normalise(raw: str) -> str:
    """The file as GitHub numbers it: BOM dropped and CRLF read as one line break, and
    nothing more. The ingesters also turn a lone CR into a line break, but GitHub does not,
    so a quote that spans one is not found here (and goes to the summary) rather than
    being given a line number that is off by one."""
    return raw.removeprefix("\ufeff").replace("\r\n", "\n")


def _summary(reason: Reason) -> Anchor:
    return Anchor(kind="summary", reason=reason)


def anchor_quote(quote: str, text: str, patch: PatchMap | None) -> Anchor:
    if not quote:
        return _summary("quote_not_found")
    first = text.find(quote)
    if first == -1:
        return _summary("quote_not_found")
    if text.find(quote, first + 1) != -1:  # overlapping matches are ambiguous too
        return _summary("ambiguous_quote")
    if patch is None:
        return _summary("no_patch")
    start_line = text.count("\n", 0, first) + 1
    end_line = text.count("\n", 0, first + len(quote) - 1) + 1
    span = range(start_line, end_line + 1)
    touched = [n for n in span if n in patch.added]
    if not touched:
        return _summary("unchanged_text")
    if all(n in patch.visible for n in span):
        return Anchor(kind="inline", start_line=start_line, end_line=end_line)
    # part of the range lies outside the diff: comment on the first line the PR wrote
    return Anchor(kind="inline", start_line=touched[0], end_line=touched[0])
