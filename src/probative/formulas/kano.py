"""Kano's evaluation table as a pure function (non-numeric, so not a formula).

Each respondent answers a functional question (how do you feel if the need is
met) and a dysfunctional one (how do you feel if it is not), both on the same
five answers. The pair is a cell in a 5 x 5 table; the cell is the category.
Olsen (2015) p. 64-65 names three of the classes and declines to give the
table; it is Berger et al. (1993), *Kano's methods for understanding
customer-defined quality*, Center for Quality Management Journal, p. 6.

The grid was checked cell by cell against that paper by the owner (2026-11-05).
`tests/formulas/test_kano.py` holds an independent copy; fix both together if a
cell is ever shown to be wrong.

The result is a class, not a number, so it is outside `Computed` and outside
`FormulaValidator`. Combining many respondents (a tally, a tie rule) is not in
Olsen and is PB18's decision.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from probative.formulas.registry import FormulaError


class UnknownKanoAnswerError(FormulaError):
    """An answer was not a `KanoAnswer`."""


class KanoAnswer(StrEnum):
    LIKE = "like"
    MUST_BE = "must_be"
    NEUTRAL = "neutral"
    LIVE_WITH = "live_with"
    DISLIKE = "dislike"


class KanoCategory(StrEnum):
    ATTRACTIVE = "attractive"
    ONE_DIMENSIONAL = "one_dimensional"
    MUST_BE = "must_be"
    INDIFFERENT = "indifferent"
    REVERSE = "reverse"
    QUESTIONABLE = "questionable"


_A, _O, _M, _I, _R, _Q = (
    KanoCategory.ATTRACTIVE,
    KanoCategory.ONE_DIMENSIONAL,
    KanoCategory.MUST_BE,
    KanoCategory.INDIFFERENT,
    KanoCategory.REVERSE,
    KanoCategory.QUESTIONABLE,
)
_ORDER: Final = tuple(KanoAnswer)

# Rows: functional answer. Columns: dysfunctional answer. Both in `_ORDER`.
_TABLE: Final = (
    (_Q, _A, _A, _A, _O),  # functional: like
    (_R, _I, _I, _I, _M),  # functional: must_be
    (_R, _I, _I, _I, _M),  # functional: neutral
    (_R, _I, _I, _I, _M),  # functional: live_with
    (_R, _R, _R, _R, _Q),  # functional: dislike
)

NodeClass = Literal["must_have", "performance", "delighter", "indifferent", "reverse"]

_NODE_CLASS: Final[dict[KanoCategory, NodeClass | None]] = {
    KanoCategory.MUST_BE: "must_have",
    KanoCategory.ONE_DIMENSIONAL: "performance",
    KanoCategory.ATTRACTIVE: "delighter",
    KanoCategory.INDIFFERENT: "indifferent",
    KanoCategory.REVERSE: "reverse",
    KanoCategory.QUESTIONABLE: None,
}


def _index(answer: object) -> int:
    if not isinstance(answer, KanoAnswer):
        raise UnknownKanoAnswerError(f"a Kano answer must be a KanoAnswer, got {answer!r}")
    return _ORDER.index(answer)


def kano_classify(functional: KanoAnswer, dysfunctional: KanoAnswer) -> KanoCategory:
    """The category of one respondent's answer pair."""
    return _TABLE[_index(functional)][_index(dysfunctional)]


def node_class(category: KanoCategory) -> NodeClass | None:
    """The `KanoClass.classification` for a category. A questionable pair is a
    contradiction: it is counted by the caller and never classified."""
    return _NODE_CLASS[category]
