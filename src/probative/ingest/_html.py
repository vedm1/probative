"""Generic HTML -> plain text (used by ado_csv's rich-text Description and
jira_xml's rendered-HTML description — as opposed to jira_csv/jira_html,
which carry wiki markup and go through `probative.ingest._wiki` instead).

Block-level tags become line breaks, everything else is stripped, and
entities are unescaped. No attempt at layout fidelity (tables, nested
lists) — this is a normalisation for evidence text, not a renderer.
"""

from __future__ import annotations

import html
import re

_BLOCK_BREAK_RE = re.compile(r"</?(?:br|p|div|li|ol|ul|h[1-6]|tr|table)\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_RUN_RE = re.compile(r"\n{3,}")


def to_text(markup: str) -> str:
    """Best-effort normalisation of an HTML fragment to plain text."""
    text = _BLOCK_BREAK_RE.sub("\n", markup)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_RUN_RE.sub("\n\n", text)
    return text.strip("\n")
