"""The formula registry: the only place a number may come from (I4).

A `Formula` is a pure function plus what the validator needs to find its
inputs in a graph. `slots=None` means the function is registered and tested but
not yet bound to graph nodes (`UNBOUND` names the phase that binds it); a
`Computed` that names an unbound formula is a violation, so this fails closed.

Units are plain strings on `Input.unit`. The only conversion the validator
performs is `percent -> fraction` (divide by 100, Olsen p. 59), and only when a
formula's `target_unit` is `fraction`. Anything else that does not match is a
violation, never a guess.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

SCALE_0_10: Final = "scale_0_10"
PERCENT: Final = "percent"
FRACTION: Final = "fraction"
DEVELOPER_WEEKS: Final = "developer_weeks"
BAND: Final = "band"

UNIT_RANGE: Final[Mapping[str, tuple[float, float]]] = MappingProxyType(
    {SCALE_0_10: (0, 10), PERCENT: (0, 100), FRACTION: (0, 1)}
)
"""The values a rating can take in each unit; the validator refuses anything outside."""


class FormulaError(ValueError):
    """A formula is malformed, duplicated or unknown."""


class FormulaInputError(FormulaError):
    """A formula was called with a value outside its domain."""


class UnknownFormulaError(FormulaError):
    """No formula is registered under this id."""


@dataclass(frozen=True)
class InputSlot:
    """Where one input comes from: a field of a graph node, optionally filtered.

    `where` maps a node field to the value it must hold, for example
    `{"dimension": "importance"}` on a `rating`.
    """

    name: str
    node_type: str
    field: str
    units: frozenset[str]
    where: Mapping[str, str] = dataclasses.field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "where", MappingProxyType(dict(self.where)))


@dataclass(frozen=True)
class Formula:
    id: str
    fn: Callable[..., float]
    slots: tuple[InputSlot, ...] | None
    target_unit: str | None
    citation: str
    construct: Literal["olsen", "probative"]
    tolerance: float = 1e-9

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise FormulaError("a formula needs an id")
        if not self.citation.strip():
            raise FormulaError(f"{self.id}: a formula needs a citation")
        if not self.tolerance > 0:
            raise FormulaError(f"{self.id}: tolerance must be positive")
        if self.construct not in ("olsen", "probative"):
            raise FormulaError(f"{self.id}: construct must be olsen or probative")
        if self.slots is not None and not self.slots:
            raise FormulaError(f"{self.id}: slots is None (unbound) or non-empty")


class Registry:
    def __init__(self) -> None:
        self._formulas: dict[str, Formula] = {}

    def register(self, formula: Formula) -> Formula:
        if formula.id in self._formulas:
            raise FormulaError(f"{formula.id} is already registered")
        self._formulas[formula.id] = formula
        return formula

    def get(self, formula_id: str) -> Formula:
        try:
            return self._formulas[formula_id]
        except KeyError:
            raise UnknownFormulaError(f"no formula is registered as {formula_id!r}") from None

    def __contains__(self, formula_id: object) -> bool:
        return formula_id in self._formulas

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._formulas))


REGISTRY: Final = Registry()

UNBOUND: Final[Mapping[str, str]] = MappingProxyType(
    {"roi": "PB25", "approximate_roi": "PB25", "invest_score": "PB26"}
)
"""Formulas with no graph binding yet, and the phase that adds the nodes they read."""
