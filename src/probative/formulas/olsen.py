"""Olsen's formulas as pure functions (*The Lean Product Playbook*, 2015).

Every function checks its own domain and raises `FormulaInputError`; none reads
a clock, a file, a random source or a model. Importing this module registers
them. Page numbers are print pages.

`invest_score` is the one Probative construct: p. 78 lists the six INVEST
properties and gives no scoring formula, so counting the met ones is ours.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from probative.formulas.registry import (
    BAND,
    FRACTION,
    PERCENT,
    REGISTRY,
    SCALE_0_10,
    Formula,
    FormulaInputError,
    InputSlot,
)


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise FormulaInputError(f"{name} must be a finite number, got {value!r}")
    return value


def _within(name: str, value: float, lo: float, hi: float) -> float:
    _finite(name, value)
    if not lo <= value <= hi:
        raise FormulaInputError(f"{name} must be in [{lo}, {hi}], got {value}")
    return value


def gap(importance: float, satisfaction: float) -> float:
    """Importance minus satisfaction, on one common scale (p. 56). May be negative."""
    return _finite("importance", importance) - _finite("satisfaction", satisfaction)


def ulwick_opportunity(importance: float, satisfaction: float) -> float:
    """`importance + max(importance - satisfaction, 0)`, on a 0-10 scale (p. 57)."""
    i = _within("importance", importance, 0, 10)
    s = _within("satisfaction", satisfaction, 0, 10)
    return i + max(i - s, 0)


def customer_value_delivered(importance: float, satisfaction: float) -> float:
    """`importance x satisfaction`, both as fractions (p. 60)."""
    return _within("importance", importance, 0, 1) * _within("satisfaction", satisfaction, 0, 1)


def opportunity_to_add_value(importance: float, satisfaction: float) -> float:
    """`importance x (1 - satisfaction)`, both as fractions (p. 60)."""
    return _within("importance", importance, 0, 1) * (
        1 - _within("satisfaction", satisfaction, 0, 1)
    )


def customer_value_created(importance: float, sat_after: float, sat_before: float) -> float:
    """`importance x (sat_after - sat_before)`, all as fractions (p. 62)."""
    return _within("importance", importance, 0, 1) * (
        _within("sat_after", sat_after, 0, 1) - _within("sat_before", sat_before, 0, 1)
    )


def roi(ret: float, investment: float) -> float:
    """`return / investment` (p. 81). Investment is developer-weeks, so it is above zero."""
    r = _finite("return", ret)
    inv = _finite("investment", investment)
    if r < 0:
        raise FormulaInputError(f"return must not be negative, got {r}")
    if inv <= 0:
        raise FormulaInputError(f"investment must be above zero, got {inv}")
    return r / inv


# Figure 6.2 (p. 84): rank by (return band, investment band); 1 is low, 3 is high.
_FIGURE_6_2 = {
    (3, 1): 1,
    (3, 2): 3,
    (3, 3): 6,
    (2, 1): 2,
    (2, 2): 5,
    (2, 3): 8,
    (1, 1): 4,
    (1, 2): 7,
    (1, 3): 9,
}


def approximate_roi(return_band: int, investment_band: int) -> int:
    """Rank 1 (best) to 9 for a return band and an investment band (p. 84)."""
    key = (_band(return_band), _band(investment_band))
    if key not in _FIGURE_6_2:
        raise FormulaInputError(f"bands must each be 1, 2 or 3, got {key}")
    return _FIGURE_6_2[key]


def _band(value: object) -> int:
    """A whole number. The validator hands formulas floats, so `3.0` is a 3; `True` is not."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise FormulaInputError(f"a band must be a whole number, got {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise FormulaInputError(f"a band must be a whole number, got {value!r}")
    return int(value)


INVEST_PROPERTIES = ("independent", "negotiable", "valuable", "estimable", "small", "testable")
_VERDICTS = frozenset({"met", "not_met", "cannot_tell"})


def invest_score(verdicts: Mapping[str, str]) -> int:
    """How many of the six INVEST properties (p. 78) are `met`, 0 to 6.

    `not_met` and `cannot_tell` both count 0. A model may supply the verdicts;
    it never supplies the count.
    """
    if set(verdicts) != set(INVEST_PROPERTIES):
        raise FormulaInputError(f"verdicts must name exactly {list(INVEST_PROPERTIES)}")
    bad = {k: v for k, v in verdicts.items() if not isinstance(v, str) or v not in _VERDICTS}
    if bad:
        raise FormulaInputError(f"unknown verdicts {bad}; use one of {sorted(_VERDICTS)}")
    return sum(1 for v in verdicts.values() if v == "met")


# -- registration ---------------------------------------------------------------


def _rating(name: str, dimension: str, units: frozenset[str]) -> InputSlot:
    return InputSlot(
        name=name, node_type="rating", field="value", units=units, where={"dimension": dimension}
    )


_ANY = frozenset({SCALE_0_10, PERCENT, FRACTION})
_FRAC = frozenset({FRACTION, PERCENT})
_TEN = frozenset({SCALE_0_10})

REGISTRY.register(
    Formula(
        id="gap",
        fn=gap,
        slots=(
            _rating("importance", "importance", _ANY),
            _rating("satisfaction", "satisfaction", _ANY),
        ),
        target_unit=None,
        citation="p. 56",
        construct="olsen",
    )
)
REGISTRY.register(
    Formula(
        id="ulwick_opportunity",
        fn=ulwick_opportunity,
        slots=(
            _rating("importance", "importance", _TEN),
            _rating("satisfaction", "satisfaction", _TEN),
        ),
        target_unit=SCALE_0_10,
        citation="p. 57",
        construct="olsen",
    )
)
REGISTRY.register(
    Formula(
        id="customer_value_delivered",
        fn=customer_value_delivered,
        slots=(
            _rating("importance", "importance", _FRAC),
            _rating("satisfaction", "satisfaction", _FRAC),
        ),
        target_unit=FRACTION,
        citation="p. 60",
        construct="olsen",
    )
)
REGISTRY.register(
    Formula(
        id="opportunity_to_add_value",
        fn=opportunity_to_add_value,
        slots=(
            _rating("importance", "importance", _FRAC),
            _rating("satisfaction", "satisfaction", _FRAC),
        ),
        target_unit=FRACTION,
        citation="p. 60",
        construct="olsen",
    )
)
REGISTRY.register(
    Formula(
        id="customer_value_created",
        fn=customer_value_created,
        slots=(
            _rating("importance", "importance", _FRAC),
            _rating("satisfaction_after", "satisfaction", _FRAC),
            _rating("satisfaction_before", "satisfaction", _FRAC),
        ),
        target_unit=FRACTION,
        citation="p. 62",
        construct="olsen",
    )
)
REGISTRY.register(
    Formula(id="roi", fn=roi, slots=None, target_unit=None, citation="p. 81", construct="olsen")
)
REGISTRY.register(
    Formula(
        id="approximate_roi",
        fn=approximate_roi,
        slots=None,
        target_unit=BAND,
        citation="p. 84",
        construct="olsen",
    )
)
REGISTRY.register(
    Formula(
        id="invest_score",
        fn=invest_score,
        slots=None,
        target_unit=None,
        citation="p. 78",
        construct="probative",
    )
)
