"""The acceptance rule for flagged replies (tests/critics/_flagged.py), unit-tested on
synthetic results: it was written before any flagged recording and must say what it says."""

from __future__ import annotations

from typing import Any

from tests.critics._flagged import acceptable


def _res(caught: int, fp: int, cannot_tell: int = 0, file_caught: bool = False) -> dict[str, Any]:
    return {
        "seeded": {
            "caught": caught,
            "files": [{"file": "a.json", "caught": file_caught, "cannot_tell": cannot_tell}],
        },
        "clean": {"flagged_candidates": fp},
    }


def test_equal_results_are_acceptable() -> None:
    assert acceptable(_res(12, 0), _res(12, 0))[0]


def test_one_fewer_catch_and_one_more_false_positive_are_tolerated() -> None:
    assert acceptable(_res(12, 0), _res(11, 1))[0]


def test_two_fewer_catches_is_not_acceptable() -> None:
    assert not acceptable(_res(12, 0), _res(10, 0))[0]


def test_two_more_false_positives_is_not_acceptable() -> None:
    assert not acceptable(_res(12, 0), _res(12, 2))[0]


def test_a_seeded_defect_passed_by_cannot_tell_is_not_acceptable() -> None:
    assert not acceptable(_res(12, 0), _res(12, 0, cannot_tell=1))[0]


def test_a_cannot_tell_on_a_defect_that_was_still_caught_is_not_a_silent_pass() -> None:
    assert acceptable(_res(12, 0), _res(12, 0, cannot_tell=2, file_caught=True))[0]
