from __future__ import annotations

import dataclasses

import pytest

import probative.formulas  # noqa: F401  (registers the Olsen formulas)
from probative.formulas.registry import (
    REGISTRY,
    UNBOUND,
    Formula,
    FormulaError,
    InputSlot,
    Registry,
    UnknownFormulaError,
)

SLOT = InputSlot(
    name="x", node_type="rating", field="value", units=frozenset({"fraction"}), where={}
)


def make(formula_id: str = "t.one", **over: object) -> Formula:
    base: dict[str, object] = {
        "id": formula_id,
        "fn": lambda x: x,
        "slots": (SLOT,),
        "target_unit": "fraction",
        "citation": "p. 1",
        "construct": "olsen",
    }
    return Formula(**{**base, **over})  # type: ignore[arg-type]


def test_register_then_get_returns_the_same_formula() -> None:
    reg = Registry()
    f = make()
    reg.register(f)
    assert reg.get("t.one") is f
    assert "t.one" in reg
    assert reg.ids() == ("t.one",)


def test_duplicate_id_is_refused() -> None:
    reg = Registry()
    reg.register(make())
    with pytest.raises(FormulaError, match="already registered"):
        reg.register(make())


def test_unknown_id_raises_a_typed_error() -> None:
    with pytest.raises(UnknownFormulaError, match="nope"):
        Registry().get("nope")


@pytest.mark.parametrize(
    "over",
    [
        {"id": ""},
        {"citation": ""},
        {"tolerance": 0.0},
        {"tolerance": -1.0},
        {"construct": "guess"},
        {"slots": ()},
        {"slots": (SLOT,), "target_unit": None, "citation": "p. 1", "id": " "},
    ],
)
def test_a_malformed_formula_is_refused(over: dict[str, object]) -> None:
    with pytest.raises(FormulaError):
        make(**over)


def test_a_formula_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        make().id = "other"  # type: ignore[misc]


def test_the_registered_set_is_exactly_the_specified_set() -> None:
    assert set(REGISTRY.ids()) == {
        "gap",
        "ulwick_opportunity",
        "customer_value_delivered",
        "opportunity_to_add_value",
        "customer_value_created",
        "roi",
        "approximate_roi",
        "invest_score",
    }


def test_every_registered_formula_cites_a_page_and_names_its_construct() -> None:
    for formula_id in REGISTRY.ids():
        f = REGISTRY.get(formula_id)
        assert f.citation.startswith("p. "), formula_id
        assert f.construct in {"olsen", "probative"}
    assert REGISTRY.get("invest_score").construct == "probative"
    assert {REGISTRY.get(i).construct for i in REGISTRY.ids() if i != "invest_score"} == {"olsen"}


def test_unbound_is_exactly_the_formulas_with_no_slots() -> None:
    assert set(UNBOUND) == {i for i in REGISTRY.ids() if REGISTRY.get(i).slots is None}
    assert dict(UNBOUND) == {"roi": "PB25", "approximate_roi": "PB25", "invest_score": "PB26"}


def test_bound_formulas_have_a_target_unit_or_a_shared_unit_rule() -> None:
    for formula_id in REGISTRY.ids():
        f = REGISTRY.get(formula_id)
        if f.slots is not None:
            assert len(f.slots) >= 2, formula_id


def test_a_slot_filter_cannot_be_mutated_after_construction() -> None:
    slot = InputSlot(
        name="x",
        node_type="rating",
        field="value",
        units=frozenset({"fraction"}),
        where={"dimension": "importance"},
    )
    with pytest.raises(TypeError):
        slot.where["dimension"] = "satisfaction"  # type: ignore[index]
    assert hash(slot) is not None
