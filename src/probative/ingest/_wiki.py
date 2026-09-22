"""Jira wiki-markup -> plain text (used by jira_csv and, after its own
<br/> substitution, jira_html — both export description/comment bodies in
wiki markup rather than real HTML).

v1 scope, deliberately narrow (mirrors PB1's documented-gap approach):
list-item leaders, the common emphasis markers, image macros, links and
account mentions. Anything else (tables, panels, nested macros) passes
through verbatim rather than being silently mangled.
"""

from __future__ import annotations

import re

_LIST_LEADER_RE = re.compile(r"^[ \t]*[#*]+[ \t]+", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(?<![\w\\])([*_+^~-])(?=\S)(.*?)(?<=\S)\1(?![\w\\])")
_IMAGE_MACRO_RE = re.compile(r"!([^!\n]+)!")
_LINK_RE = re.compile(r"\[([^\]|\n]+)\|[^\]\n]*\]")
_MENTION_RE = re.compile(r"\[~[^\]\n]*\]")


def to_text(markup: str) -> str:
    """Best-effort normalisation of Jira wiki markup to plain text."""
    text = markup
    text = _MENTION_RE.sub("", text)
    text = _IMAGE_MACRO_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _LIST_LEADER_RE.sub("", text)
    text = _EMPHASIS_RE.sub(r"\2", text)
    return text
