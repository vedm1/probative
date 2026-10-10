"""PB35-p1: which new-side lines a PR's `patch` makes visible, and which it adds."""

from __future__ import annotations

from probative.interfaces.github.patch import parse_patch
from tests.github.conftest import make_patch


def test_a_new_file_adds_every_line() -> None:
    patch = parse_patch(make_patch("", "a\nb\nc\n"))
    assert patch.added == frozenset({1, 2, 3})
    assert patch.visible == frozenset({1, 2, 3})


def test_context_is_visible_but_not_added() -> None:
    old = "one\ntwo\nthree\nfour\nfive\n"
    new = "one\ntwo\nTHREE\nfour\nfive\n"
    patch = parse_patch(make_patch(old, new))
    assert patch.added == frozenset({3})
    assert patch.visible == frozenset({1, 2, 3, 4, 5})


def test_removed_lines_take_no_new_side_number() -> None:
    old = "a\nb\nc\nd\n"
    new = "a\nc\nd\n"
    patch = parse_patch(make_patch(old, new))
    assert patch.added == frozenset()
    assert patch.visible == frozenset({1, 2, 3})


def test_two_hunks_leave_a_gap_that_is_not_visible() -> None:
    old = "\n".join(f"l{i}" for i in range(1, 41)) + "\n"
    changed = old.replace("l2\n", "L2\n").replace("l38\n", "L38\n")
    patch = parse_patch(make_patch(old, changed))
    assert patch.added == frozenset({2, 38})
    assert 20 not in patch.visible
    assert {1, 5, 35, 40} <= patch.visible


def test_no_newline_marker_is_ignored() -> None:
    raw = "@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file"
    patch = parse_patch(raw)
    assert patch.added == frozenset({1})


def test_a_blank_context_line_with_its_space_stripped_still_counts() -> None:
    raw = "@@ -1,2 +1,3 @@\n a\n\n+x\n"  # the middle context line lost its leading space
    patch = parse_patch(raw)
    assert patch.visible == frozenset({1, 2, 3})
    assert patch.added == frozenset({3})


def test_hunk_header_without_counts() -> None:
    patch = parse_patch("@@ -0,0 +1 @@\n+only")
    assert patch.added == frozenset({1})


def test_empty_patch_is_empty() -> None:
    patch = parse_patch("")
    assert patch.added == frozenset() and patch.visible == frozenset()
