"""Confluence "Export to Word" (.doc extension, but real content is MHTML —
a multipart/related MIME message, quoted-printable, wrapping one text/html
part) extraction.

Confirmed against two real Confluence Cloud per-page exports during the
PB2-p2 build session (never committed — CLAUDE.md § Secrets): the "Word"
export is not OOXML at all (`python-docx` would reject it), and the page
itself carries no issue/hierarchy structure — it's a title plus prose
paragraphs and HTML tables. This is why PB2-p2 produces a plain `Source`
(PB1's shape), not a PB2-style derived record type.

Table rows are flattened one row per line, cells joined by " | " — a
normalisation this codebase hasn't needed before: `docx_.py` explicitly
punts on tables, and PB2's generic `_html.to_text()` doesn't separate
`<td>`/`<th>` cells at all (it was built for Jira/ADO description fields,
not full pages dominated by tables). A cell containing multiple `<p>`s
(e.g. a "Definitions" table's Audience/Stability/Support breakdown) has its
paragraphs joined with " / " to keep them distinguishable without
fabricating structure the flat-line format can't represent.
"""

from __future__ import annotations

import email
import email.policy
from email.message import Message
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from probative.core.evidence import CorruptSourceError, EmptySourceError, Locator, LocatorRegion
from probative.ingest._extracted import ExtractedDocument

NORMALIZATION_VERSION = "confluence_word/1"

_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
_BLOCK_TAGS = [*_HEADING_TAGS, "p", "table"]


def _find_html_part(msg: Message) -> Message | None:
    if msg.get_content_maintype() != "multipart":
        return None
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part
    return None


def _decode_html_part(path: Path, part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):  # pragma: no cover - defensive: no CTE-decodable payload
        raise CorruptSourceError(path, "text/html part has no decodable payload")
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset)
    except (UnicodeDecodeError, LookupError) as exc:
        raise CorruptSourceError(path, f"text/html part is not valid {charset}: {exc}") from exc


def _row_text(row: Tag) -> str:
    cells = [
        cell.get_text(separator=" / ", strip=True)
        for cell in row.find_all(["th", "td"], recursive=False)
    ]
    return " | ".join(cells)


def extract(path: Path) -> ExtractedDocument:
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    html_part = _find_html_part(msg)
    if html_part is None:
        raise CorruptSourceError(path, "no text/html part found in Confluence Word export")

    html_text = _decode_html_part(path, html_part)
    soup = BeautifulSoup(html_text, "html.parser")
    body = soup.find("body")
    if not isinstance(body, Tag):
        raise CorruptSourceError(path, "no <body> in Confluence export HTML")

    text_parts: list[str] = []
    regions: list[LocatorRegion] = []
    offset = 0
    stack: list[tuple[int, str]] = []
    line_no = 0

    def _emit(line_text: str) -> None:
        nonlocal offset, line_no
        line_no += 1
        line = line_text + "\n"
        start = offset
        end = offset + len(line)
        offset = end
        text_parts.append(line)
        heading_path = [t for _, t in stack] or None
        regions.append(
            LocatorRegion(
                start=start, end=end, locator=Locator(line=line_no, heading_path=heading_path)
            )
        )

    for element in body.find_all(_BLOCK_TAGS):
        if element.find_parent("table") is not None:
            continue  # a <p> inside a <td>/<th> — folded into its row below

        if element.name in _HEADING_TAGS:
            level = int(element.name[1])
            title = element.get_text(strip=True)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            _emit(title)
        elif element.name == "p":
            _emit(element.get_text(strip=True))
        else:  # table
            for row in element.find_all("tr", recursive=True):
                _emit(_row_text(row))

    if not text_parts:
        raise EmptySourceError(
            path, "no extractable heading/paragraph/table content in Confluence export"
        )

    return ExtractedDocument(
        text="".join(text_parts),
        locator_regions=regions,
        normalization_version=NORMALIZATION_VERSION,
    )
