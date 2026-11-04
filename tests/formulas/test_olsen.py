"""Olsen's own worked examples (*The Lean Product Playbook*, 2015, print pages).

The page is in each test id. A figure the book rounds is compared after the
stated rounding, never with a loosened tolerance.
"""

from __future__ import annotations

import itertools
import math

import pytest

from probative.formulas.olsen import (
    approximate_roi,
    customer_value_created,
    customer_value_delivered,
    gap,
    invest_score,
    opportunity_to_add_value,
    roi,
    ulwick_opportunity,
)
from probative.formulas.registry import FormulaInputError

# -- gap: p. 56 ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("importance", "satisfaction", "want"),
    [(10, 5, 5), (6, 1, 5), (3, 8, -5)],
    ids=["p56-10-5", "p56-6-1", "p56-negative-gap"],
)
def test_gap(importance: float, satisfaction: float, want: float) -> None:
    assert gap(importance, satisfaction) == want


# -- ulwick_opportunity: p. 57 -------------------------------------------------


@pytest.mark.parametrize(
    ("importance", "satisfaction", "want"),
    [(10, 5, 15), (6, 1, 11), (0, 0, 0), (10, 0, 20), (4, 9, 4)],
    ids=["p57-10-5", "p57-6-1", "p57-min-0", "p57-max-20", "p57-negative-gap-floors-at-0"],
)
def test_ulwick_opportunity(importance: float, satisfaction: float, want: float) -> None:
    assert ulwick_opportunity(importance, satisfaction) == want


def test_ulwick_ranks_the_higher_importance_need_first_for_an_equal_gap() -> None:
    assert ulwick_opportunity(10, 5) > ulwick_opportunity(6, 1)  # p. 57
    assert gap(10, 5) == gap(6, 1)  # p. 56: the gap alone cannot tell them apart


# -- the 0-1 product formulas: p. 60-63 ----------------------------------------


def test_customer_value_delivered_p60() -> None:
    assert customer_value_delivered(0.7, 0.7) == pytest.approx(0.49)


def test_opportunity_to_add_value_p61() -> None:
    assert opportunity_to_add_value(0.7, 0.7) == pytest.approx(0.21)
    assert opportunity_to_add_value(0.9, 0.3) == pytest.approx(0.63)


def test_opportunity_b_is_three_times_a_p61() -> None:
    assert opportunity_to_add_value(0.9, 0.3) / opportunity_to_add_value(0.7, 0.7) == pytest.approx(
        3
    )


def test_feature_x_p62_is_rounded_by_the_book_to_two_places() -> None:
    value = opportunity_to_add_value(0.82, 0.55)
    assert value == pytest.approx(0.369)
    assert round(value, 2) == 0.37


def test_customer_value_created_p63() -> None:
    assert customer_value_created(0.7, 0.9, 0.7) == pytest.approx(0.14)


def test_customer_value_created_is_negative_when_satisfaction_falls() -> None:
    assert customer_value_created(0.7, 0.5, 0.7) == pytest.approx(-0.14)


GRID = [0.0, 0.1, 0.25, 0.5, 0.7, 0.9, 1.0]


def test_opportunity_is_importance_minus_value_delivered_p62() -> None:
    for i, s in itertools.product(GRID, GRID):
        assert opportunity_to_add_value(i, s) == pytest.approx(i - customer_value_delivered(i, s))


def test_value_created_from_zero_equals_value_delivered() -> None:
    for i, s in itertools.product(GRID, GRID):
        assert customer_value_created(i, s, 0.0) == pytest.approx(customer_value_delivered(i, s))


# -- roi: p. 81-83 -------------------------------------------------------------


@pytest.mark.parametrize(
    ("ret", "investment", "want"),
    [(6, 2, 3), (6, 4, 1.5), (4, 4, 1), (8, 8, 1), (2, 8, 0.25)],
    ids=["p82-A", "p82-B", "p82-C", "p82-D", "p83-F"],
)
def test_roi(ret: float, investment: float, want: float) -> None:
    assert roi(ret, investment) == want


# -- approximate_roi: p. 84, Figure 6.2 ----------------------------------------

LOW, MEDIUM, HIGH = 1, 2, 3
FIGURE_6_2 = {
    (HIGH, LOW): 1,
    (HIGH, MEDIUM): 3,
    (HIGH, HIGH): 6,
    (MEDIUM, LOW): 2,
    (MEDIUM, MEDIUM): 5,
    (MEDIUM, HIGH): 8,
    (LOW, LOW): 4,
    (LOW, MEDIUM): 7,
    (LOW, HIGH): 9,
}


@pytest.mark.parametrize(("cell", "want"), sorted(FIGURE_6_2.items()))
def test_approximate_roi_figure_6_2_p84(cell: tuple[int, int], want: int) -> None:
    assert approximate_roi(*cell) == want


def test_approximate_roi_uses_each_rank_once() -> None:
    assert sorted(approximate_roi(r, i) for r, i in itertools.product((1, 2, 3), repeat=2)) == list(
        range(1, 10)
    )


# -- invest_score: p. 78 lists the properties; the count is a Probative construct --

PROPS = ("independent", "negotiable", "valuable", "estimable", "small", "testable")


def verdicts(**over: str) -> dict[str, str]:
    return {**dict.fromkeys(PROPS, "met"), **over}


def test_invest_score_counts_met_properties() -> None:
    assert invest_score(verdicts()) == 6
    assert invest_score(verdicts(small="not_met")) == 5
    assert invest_score(dict.fromkeys(PROPS, "not_met")) == 0


def test_invest_score_counts_cannot_tell_as_not_met() -> None:
    assert invest_score(verdicts(testable="cannot_tell", small="cannot_tell")) == 4


@pytest.mark.parametrize(
    "bad",
    [
        {k: v for k, v in verdicts().items() if k != "small"},
        {**verdicts(), "extra": "met"},
        verdicts(small="maybe"),
        {},
    ],
    ids=["missing-key", "extra-key", "unknown-verdict", "empty"],
)
def test_invest_score_refuses_a_malformed_verdict_map(bad: dict[str, str]) -> None:
    with pytest.raises(FormulaInputError):
        invest_score(bad)


# -- domains and determinism ---------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: ulwick_opportunity(11, 5),
        lambda: ulwick_opportunity(5, -1),
        lambda: customer_value_delivered(1.1, 0.5),
        lambda: customer_value_delivered(0.5, -0.1),
        lambda: opportunity_to_add_value(0.5, 1.5),
        lambda: customer_value_created(0.5, 0.5, 2),
        lambda: roi(6, 0),
        lambda: roi(6, -1),
        lambda: roi(-1, 2),
        lambda: approximate_roi(0, 1),
        lambda: approximate_roi(1, 4),
        lambda: gap(math.nan, 1),
        lambda: roi(math.inf, 1),
    ],
    ids=[
        "ulwick-i-high",
        "ulwick-s-low",
        "cvd-i-high",
        "cvd-s-low",
        "otav-s-high",
        "cvc-s-high",
        "roi-zero-investment",
        "roi-negative-investment",
        "roi-negative-return",
        "band-low",
        "band-high",
        "gap-nan",
        "roi-inf",
    ],
)
def test_out_of_domain_input_raises(call: object) -> None:
    with pytest.raises(FormulaInputError):
        call()  # type: ignore[operator]


def test_the_functions_are_deterministic() -> None:
    assert len({opportunity_to_add_value(0.82, 0.55) for _ in range(5)}) == 1


@pytest.mark.parametrize("bands", [(True, True), (2.5, 1), (1, 3.5), ("3", 1), (None, 1)], ids=str)
def test_approximate_roi_refuses_a_bool_or_a_non_integral_band(
    bands: tuple[object, object],
) -> None:
    with pytest.raises(FormulaInputError):
        approximate_roi(*bands)  # type: ignore[arg-type]


def test_approximate_roi_accepts_an_integral_float_band() -> None:
    assert approximate_roi(3.0, 1.0) == 1  # type: ignore[arg-type]  # the validator passes floats


def test_invest_score_refuses_an_unhashable_verdict() -> None:
    with pytest.raises(FormulaInputError):
        invest_score({**verdicts(), "small": ["met"]})  # type: ignore[dict-item]
