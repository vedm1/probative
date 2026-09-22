"""Unit tests for probative.ingest._wiki.to_text's documented markup rules."""

from __future__ import annotations

from probative.ingest._wiki import to_text


def test_ordered_list_leaders_stripped() -> None:
    assert to_text("# first\n# second") == "first\nsecond"


def test_unordered_list_leaders_stripped() -> None:
    assert to_text("* first\n* second") == "first\nsecond"


def test_bold_emphasis_stripped() -> None:
    assert to_text("this is *important* text") == "this is important text"


def test_italic_emphasis_stripped() -> None:
    assert to_text("this is _important_ text") == "this is important text"


def test_image_macro_dropped() -> None:
    assert to_text("see !screenshot.png! for details") == "see  for details"


def test_link_keeps_display_text_drops_url() -> None:
    assert to_text("see [the docs|https://example.com/docs]") == "see the docs"


def test_account_mention_dropped() -> None:
    assert to_text("cc [~accountid:abc123] please review") == "cc  please review"


def test_plain_text_passes_through_unchanged() -> None:
    text = "Nothing to normalise here."
    assert to_text(text) == text
