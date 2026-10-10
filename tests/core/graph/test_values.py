from __future__ import annotations

import pytest
from pydantic import ValidationError

from probative.core.graph.values import Computed, Input


def test_input_needs_a_unit_and_provenance() -> None:
    with pytest.raises(ValidationError):
        Input(value=1, unit="", provenance="elicited")
    with pytest.raises(ValidationError):
        Input(value=1, unit="days", provenance="")


def test_computed_needs_a_formula_id() -> None:
    with pytest.raises(ValidationError):
        Computed(value=1.0, formula_id="", input_ids=[])
    assert (
        Computed(value=1.0, formula_id="f.v1", input_ids=["claim_aaaaaaaaaaaa"]).formula_id
        == "f.v1"
    )


def test_wrappers_are_frozen() -> None:
    c = Computed(value=1.0, formula_id="f.v1", input_ids=[])
    with pytest.raises(ValidationError):
        c.value = 2.0  # type: ignore[misc]
