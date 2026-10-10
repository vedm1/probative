"""PB35-p1: placing a verified quote on a line of the PR's file, or declining to.

`source.text` is the normalised text, not the file bytes, so anchoring searches the
quote in the normalised file and refuses anything that is not a unique match on a
line the PR added (I1: a downgrade to the summary is allowed, an invented line is not).
"""

from __future__ import annotations

from probative.interfaces.github.anchor import anchor_quote, normalise
from probative.interfaces.github.patch import PatchMap, parse_patch
from tests.github.conftest import make_patch

TEXT = "# Title\n\nUsers need a dashboard.\nShoppers pay fast.\nUsers need a dashboard too.\n"


def _all_added(text: str) -> PatchMap:
    return parse_patch(make_patch("", text))


def test_unique_quote_on_an_added_line_is_inline() -> None:
    anchor = anchor_quote("Shoppers pay fast.", TEXT, _all_added(TEXT))
    assert anchor.kind == "inline"
    assert (anchor.start_line, anchor.end_line) == (4, 4)
    assert anchor.reason is None


def test_ambiguous_quote_goes_to_the_summary() -> None:
    anchor = anchor_quote("Users need a dashboard", TEXT, _all_added(TEXT))
    assert (anchor.kind, anchor.reason) == ("summary", "ambiguous_quote")


def test_overlapping_matches_count_as_ambiguous() -> None:
    anchor = anchor_quote("aa", "aaa\n", _all_added("aaa\n"))
    assert anchor.reason == "ambiguous_quote"


def test_quote_not_in_the_file_is_not_found() -> None:
    anchor = anchor_quote("never written", TEXT, _all_added(TEXT))
    assert (anchor.kind, anchor.reason) == ("summary", "quote_not_found")


def test_quote_on_a_context_line_is_unchanged_text() -> None:
    old = "# Title\n\nUsers need a dashboard.\nShoppers pay fast.\n"
    new = old + "A new closing line.\n"
    anchor = anchor_quote("Shoppers pay fast.", new, parse_patch(make_patch(old, new)))
    assert (anchor.kind, anchor.reason) == ("summary", "unchanged_text")


def test_a_multi_line_quote_spanning_added_lines_is_a_range() -> None:
    quote = "Users need a dashboard too.\nSecond line."
    text = "intro\n" + quote + "\nend\n"
    anchor = anchor_quote(quote, text, _all_added(text))
    assert (anchor.kind, anchor.start_line, anchor.end_line) == ("inline", 2, 3)


def test_a_range_that_leaves_the_diff_is_cut_back_to_one_added_line() -> None:
    old = "\n".join(f"l{i}" for i in range(1, 41)) + "\n"
    new = old.replace("l2\n", "L2\n").replace("l38\n", "L38\n")
    quote = new.split("\n", 2)[1] + "\n" + "\n".join(new.split("\n")[2:20])  # lines 2..20
    anchor = anchor_quote(quote, new, parse_patch(make_patch(old, new)))
    assert anchor.kind == "inline"
    assert anchor.start_line == anchor.end_line == 2


def test_no_patch_is_summary() -> None:
    anchor = anchor_quote("Shoppers pay fast.", TEXT, None)
    assert (anchor.kind, anchor.reason) == ("summary", "no_patch")


def test_normalise_only_changes_what_github_does_not_count_as_a_line() -> None:
    # GitHub numbers lines by "\n" alone, so a lone "\r" must stay where it is
    assert normalise("\ufeffa\r\nb\rc\n") == "a\nb\rc\n"


def test_a_lone_carriage_return_cannot_shift_the_line() -> None:
    text = normalise("a\nold line one\rQUOTE ME here\nz\n")
    anchor = anchor_quote("QUOTE ME here", text, _all_added(text))
    assert (anchor.start_line, anchor.end_line) == (2, 2)
    # the ingester turns the lone "\r" into "\n": that quote is not in the file as GitHub sees it
    split = anchor_quote("old line one\nQUOTE ME here", text, _all_added(text))
    assert (split.kind, split.reason) == ("summary", "quote_not_found")


def test_crlf_file_anchors_on_the_normalised_line() -> None:
    raw = "# T\r\n\r\nShoppers pay fast.\r\n"
    text = normalise(raw)
    anchor = anchor_quote("Shoppers pay fast.", text, _all_added(text))
    assert (anchor.start_line, anchor.end_line) == (3, 3)


def test_an_empty_quote_is_never_anchored() -> None:
    anchor = anchor_quote("", TEXT, _all_added(TEXT))
    assert (anchor.kind, anchor.reason) == ("summary", "quote_not_found")
