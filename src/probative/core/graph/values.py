"""The only two carriers of a number in the graph (I4), and shared field types.

`Input` is something a person or a model *proposes* (a cost, a count, a rating
a customer gave). `Computed` is an output: it names the registered pure
function (PB11) that produces it and the node ids that function read. A node
holding a bare `int`/`float` is a structural-test failure, so there is no
third way to put a number in the graph.

Numbers are real numbers: strict (no `True`, no `"5"`) and finite (no NaN or
infinity, which are not JSON and break equality).

Not enforced here: that a `Computed` value is *correct*, or that `formula_id`
names a registered function. That is `FormulaValidator` (PB11); until it
exists, `validators.unverified_computed` lists every such value.
"""

from __future__ import annotations

from datetime import UTC
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
)

from probative.core.graph._ids import ID_REGEX

Ref = Annotated[str, StringConstraints(pattern=ID_REGEX)]
"""A graph id."""

UtcDatetime = Annotated[AwareDatetime, AfterValidator(lambda d: d.astimezone(UTC))]
"""One instant is one value, and one serialisation, whatever offset it arrived with."""

_Real = StrictInt | Annotated[float, Field(strict=True, allow_inf_nan=False)]


class Input(BaseModel):
    """A proposed or authored quantity. Never an output of arithmetic."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: _Real
    unit: str = Field(min_length=1)
    provenance: str = Field(min_length=1)  # "elicited" or the id of the node it came from


class Computed(BaseModel):
    """An output of a registered formula. `FormulaValidator` (PB11) recomputes
    `value` from `input_ids` and diffs it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: StrictBool | _Real | None
    formula_id: str = Field(min_length=1)
    input_ids: tuple[Ref, ...]
