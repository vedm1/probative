"""Windowing a Source for per-call size limits (extract/chunking.py)."""

from __future__ import annotations

from itertools import pairwise

from probative.core.evidence import Locator
from probative.extract.chunking import chunk_windows
from tests.extract._helpers import make_source


def _assert_covers(windows: list[tuple[int, int]], length: int) -> None:
    assert windows[0][0] == 0
    assert windows[-1][1] == length
    for (_, prev_end), (next_start, _) in pairwise(windows):
        assert prev_end == next_start


def test_small_document_is_one_window() -> None:
    source = make_source("hello world")
    assert chunk_windows(source, max_chars=100) == [(0, 11)]


def test_splits_at_region_boundaries() -> None:
    text = "a" * 40 + "b" * 40 + "c" * 40
    regions = [(0, 40, Locator(page=1)), (40, 80, Locator(page=2)), (80, 120, Locator(page=3))]
    source = make_source(text, regions=regions)
    windows = chunk_windows(source, max_chars=80)
    assert windows == [(0, 80), (80, 120)]
    _assert_covers(windows, len(text))


def test_oversize_region_splits_at_paragraph_break() -> None:
    para = "word " * 10
    text = para + "\n\n" + para + "\n\n" + para
    source = make_source(text)
    windows = chunk_windows(source, max_chars=len(para) + 5)
    _assert_covers(windows, len(text))
    assert len(windows) == 3
    for start, end in windows[:-1]:
        assert text[start:end].endswith("\n\n")
    assert all(end - start <= len(para) + 5 for start, end in windows)


def test_oversize_region_without_paragraphs_splits_at_line_break() -> None:
    text = "\n".join(["line of text number"] * 10) + "\n"
    source = make_source(text)
    windows = chunk_windows(source, max_chars=60)
    _assert_covers(windows, len(text))
    assert all(text[start:end].endswith("\n") for start, end in windows)
    assert all(end - start <= 60 for start, end in windows)


def test_a_line_longer_than_the_budget_is_hard_split() -> None:
    text = "x" * 250
    source = make_source(text)
    windows = chunk_windows(source, max_chars=100)
    _assert_covers(windows, 250)
    assert windows == [(0, 100), (100, 200), (200, 250)]


def test_non_positive_budget_is_a_value_error_not_an_infinite_loop() -> None:
    import pytest

    source = make_source("some text")
    for bad in (0, -1):
        with pytest.raises(ValueError, match="max_chars"):
            chunk_windows(source, max_chars=bad)
