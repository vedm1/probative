from __future__ import annotations

import pytest

from probative.formulas.olsen import opportunity_to_add_value, ulwick_opportunity
from probative.formulas.ranking import top_n, top_n_disagree


def test_top_n_is_descending_with_ties_broken_by_id() -> None:
    scores = {"b": 2.0, "a": 2.0, "c": 5.0, "d": 1.0}
    assert top_n(scores, 3) == ("c", "a", "b")


def test_top_n_larger_than_the_set_returns_everything() -> None:
    assert top_n({"a": 1.0}, 5) == ("a",)


@pytest.mark.parametrize("n", [0, -1])
def test_top_n_refuses_a_non_positive_n(n: int) -> None:
    with pytest.raises(ValueError, match="n must be"):
        top_n({"a": 1.0}, n)


def test_no_disagreement_when_both_rank_the_same() -> None:
    s = {"a": 3.0, "b": 2.0, "c": 1.0}
    assert top_n_disagree(s, dict(s), n=2) == ()


def test_the_two_opportunity_formulas_disagree_on_the_books_own_pair() -> None:
    # Olsen p. 56-57: a need at importance 10, satisfaction 5 and one at 6 and 1.
    needs = {"n_10_5": (10, 5), "n_6_1": (6, 1)}
    ulwick = {k: ulwick_opportunity(i, s) for k, (i, s) in needs.items()}
    product = {k: opportunity_to_add_value(i / 10, s / 10) for k, (i, s) in needs.items()}
    assert top_n(ulwick, 1) == ("n_10_5",)  # 15 against 11
    assert top_n(product, 1) == ("n_6_1",)  # 0.54 against 0.50
    assert top_n_disagree(ulwick, product, n=1) == ("n_10_5", "n_6_1")


def test_disagreement_is_sorted_and_covers_both_directions() -> None:
    a = {"x": 3.0, "y": 2.0, "z": 1.0}
    b = {"x": 3.0, "y": 1.0, "z": 2.0}
    assert top_n_disagree(a, b, n=2) == ("y", "z")
