"""Unit tests for probative.ingest._html.to_text's documented rules."""

from __future__ import annotations

from probative.ingest._html import to_text


def test_paragraph_tags_become_line_breaks() -> None:
    assert to_text("<p>first</p><p>second</p>") == "first\n\nsecond"


def test_div_tags_become_line_breaks() -> None:
    assert to_text("<div>first</div><div>second</div>") == "first\n\nsecond"


def test_br_becomes_newline() -> None:
    assert to_text("first<br/>second") == "first\nsecond"


def test_list_items_become_lines() -> None:
    assert to_text("<ol><li>first</li><li>second</li></ol>") == "first\n\nsecond"


def test_entities_are_unescaped() -> None:
    assert to_text("a&nbsp;b &amp; c") == "a b & c"  # noqa: RUF001


def test_unknown_inline_tags_are_stripped() -> None:
    assert to_text("<span>bold <b>text</b></span>") == "bold text"


def test_plain_text_passes_through_unchanged() -> None:
    assert to_text("Nothing to normalise here.") == "Nothing to normalise here."
