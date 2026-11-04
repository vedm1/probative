from __future__ import annotations

import pytest

import probative.formulas  # noqa: F401  (registers the Olsen formulas)
from probative.core.evidence import EvidenceKind, Tier
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, NodeBase, Opportunity, Rating
from probative.core.graph.validators import Violation
from probative.core.graph.values import Computed
from probative.formulas.registry import Formula, InputSlot, Registry
from probative.formulas.validator import FormulaValidator
from tests.core.graph._samples import ENV, inp


def rating(dimension: str, value: float, unit: str) -> Rating:
    return Rating.make(
        dimension=dimension,
        value=inp(value, unit),
        n=inp(12),
        dispersion=inp(1.0, "stdev"),
        tier=Tier.T1,
        evidence_kind=EvidenceKind.CUSTOMER,
        **ENV,
    )


def opp(formula_id: str, value: float | None, inputs: list[NodeBase]) -> Opportunity:
    return Opportunity.make(
        value=Computed(value=value, formula_id=formula_id, input_ids=[n.id for n in inputs]), **ENV
    )


def graph(*nodes: NodeBase) -> Graph:
    return Graph.empty().with_patch(nodes=list(nodes))


def check(*nodes: NodeBase) -> list[Violation]:
    return FormulaValidator().check(graph(*nodes))


def codes(vs: list[Violation]) -> list[str]:
    return [v.code for v in vs]


# -- every bound formula, on the book's numbers ---------------------------------


def test_each_bound_formula_verifies_on_a_book_example() -> None:
    cases: list[tuple[str, float, list[Rating]]] = [
        (
            "gap",
            5,
            [rating("importance", 10, "scale_0_10"), rating("satisfaction", 5, "scale_0_10")],
        ),
        (
            "ulwick_opportunity",
            15,
            [rating("importance", 10, "scale_0_10"), rating("satisfaction", 5, "scale_0_10")],
        ),
        (
            "customer_value_delivered",
            0.49,
            [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")],
        ),
        (
            "opportunity_to_add_value",
            0.63,
            [rating("importance", 0.9, "fraction"), rating("satisfaction", 0.3, "fraction")],
        ),
        (
            "customer_value_created",
            0.14,
            [
                rating("importance", 0.7, "fraction"),
                rating("satisfaction", 0.9, "fraction"),
                rating("satisfaction", 0.7, "fraction"),
            ],
        ),
    ]
    for formula_id, want, inputs in cases:
        assert check(opp(formula_id, want, list(inputs)), *inputs) == [], formula_id


def test_a_hand_edited_value_is_a_mismatch() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    (v,) = check(opp("customer_value_delivered", 0.50, inputs), *inputs)
    assert (v.invariant, v.code) == ("I4", "I4_VALUE_MISMATCH")
    assert "0.5" in v.message and "0.49" in v.message


def test_percent_input_gives_the_same_result_as_fraction_input() -> None:
    inputs = [rating("importance", 70, "percent"), rating("satisfaction", 70, "percent")]
    assert check(opp("customer_value_delivered", 0.49, inputs), *inputs) == []


def test_the_tolerance_is_tight() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    assert codes(check(opp("customer_value_delivered", 0.49 + 1e-6, inputs), *inputs)) == [
        "I4_VALUE_MISMATCH"
    ]


# -- one case per other code ----------------------------------------------------


def test_unknown_formula() -> None:
    inputs = [rating("importance", 1, "fraction")]
    assert codes(check(opp("made.up.v1", 1.0, inputs), *inputs)) == ["I4_UNKNOWN_FORMULA"]


@pytest.mark.parametrize("formula_id", ["roi", "approximate_roi", "invest_score"])
def test_an_unbound_formula_fails_closed(formula_id: str) -> None:
    inputs = [rating("importance", 1, "fraction")]
    assert codes(check(opp(formula_id, 1.0, inputs), *inputs)) == ["I4_UNBOUND_FORMULA"]


def test_claim_confidence_is_unregistered_until_pb13() -> None:
    claim = Claim.make(
        text="x",
        tier=Tier.T3,
        confidence=Computed(value=0.5, formula_id="confidence.v1", input_ids=[]),
        **ENV,
    )
    assert codes(check(claim)) == ["I4_UNKNOWN_FORMULA"]


def test_wrong_number_of_inputs() -> None:
    inputs = [rating("importance", 0.7, "fraction")]
    assert codes(check(opp("customer_value_delivered", 0.7, inputs), *inputs)) == ["I4_INPUT_ARITY"]


def test_input_of_the_wrong_dimension_or_node_type() -> None:
    two_importances = [rating("importance", 0.7, "fraction"), rating("importance", 0.6, "fraction")]
    assert codes(
        check(opp("customer_value_delivered", 0.4, two_importances), *two_importances)
    ) == ["I4_INPUT_TYPE"]
    swapped = [rating("satisfaction", 0.7, "fraction"), rating("importance", 0.7, "fraction")]
    assert codes(check(opp("customer_value_delivered", 0.49, swapped), *swapped)) == [
        "I4_INPUT_TYPE",
        "I4_INPUT_TYPE",
    ]
    claim = Claim.make(
        text="x",
        tier=Tier.T3,
        confidence=Computed(value=0.5, formula_id="confidence.v1", input_ids=[]),
        **ENV,
    )
    mixed = [claim, rating("satisfaction", 0.7, "fraction")]
    assert "I4_INPUT_TYPE" in codes(check(opp("customer_value_delivered", 0.0, mixed), *mixed))


def test_unit_not_accepted_by_the_formula() -> None:
    ulwick = [rating("importance", 10, "percent"), rating("satisfaction", 5, "percent")]
    assert codes(check(opp("ulwick_opportunity", 15, ulwick), *ulwick)) == [
        "I4_INPUT_UNIT",
        "I4_INPUT_UNIT",
    ]
    ten = [rating("importance", 0.7, "scale_0_10"), rating("satisfaction", 0.7, "scale_0_10")]
    assert "I4_INPUT_UNIT" in codes(check(opp("customer_value_delivered", 0.49, ten), *ten))


def test_gap_needs_both_inputs_in_one_unit() -> None:
    mixed = [rating("importance", 70, "percent"), rating("satisfaction", 0.5, "fraction")]
    assert codes(check(opp("gap", 0.2, mixed), *mixed)) == ["I4_INPUT_UNIT"]


def test_input_out_of_range() -> None:
    inputs = [rating("importance", 1.5, "fraction"), rating("satisfaction", 0.5, "fraction")]
    assert codes(check(opp("customer_value_delivered", 0.75, inputs), *inputs)) == [
        "I4_INPUT_RANGE"
    ]


def test_stored_value_missing() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    assert codes(check(opp("customer_value_delivered", None, inputs), *inputs)) == ["I4_VALUE_TYPE"]


def test_stored_value_a_bool() -> None:
    inputs = [rating("importance", 1, "fraction"), rating("satisfaction", 1, "fraction")]
    node = Opportunity.make(
        value=Computed(
            value=True, formula_id="customer_value_delivered", input_ids=[n.id for n in inputs]
        ),
        **ENV,
    )
    assert codes(check(node, *inputs)) == ["I4_VALUE_TYPE"]


def test_a_dangling_input_is_left_to_the_shape_check() -> None:
    node = Opportunity.make(
        value=Computed(
            value=1.0, formula_id="customer_value_delivered", input_ids=["rating_ffffffffffff"]
        ),
        **ENV,
    )
    assert check(node) == []


def test_a_custom_registry_is_honoured() -> None:
    reg = Registry()
    reg.register(
        Formula(
            id="double",
            fn=lambda x: x * 2,
            slots=(
                InputSlot(
                    name="x",
                    node_type="rating",
                    field="value",
                    units=frozenset({"fraction"}),
                    where={"dimension": "importance"},
                ),
            ),
            target_unit="fraction",
            citation="p. 0",
            construct="probative",
        )
    )
    r = rating("importance", 0.25, "fraction")
    assert FormulaValidator(reg).check(graph(opp("double", 0.5, [r]), r)) == []
    assert (
        FormulaValidator(reg).check(graph(opp("double", 0.6, [r]), r))[0].code
        == "I4_VALUE_MISMATCH"
    )


def test_violations_are_sorted_and_repeatable() -> None:
    a = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    g = graph(opp("customer_value_delivered", 0.1, a), *a)
    first = FormulaValidator().check(g)
    assert first == FormulaValidator().check(g)
    assert first == sorted(first, key=lambda v: (v.invariant, v.code, v.node_id, v.message))


# -- recompute -> with_recomputed -> check --------------------------------------


def test_recompute_round_trip_is_clean_and_id_stable() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    bad = opp("customer_value_delivered", 0.99, inputs)
    g = graph(bad, *inputs)
    v = FormulaValidator()
    fixes = v.recompute(g)
    assert set(fixes) == {bad.id}
    fixed = g.with_recomputed(fixes)
    assert v.check(fixed) == []
    assert set(fixed.nodes) == set(g.nodes)
    stored = fixed.nodes[bad.id]
    assert isinstance(stored, Opportunity)
    assert stored.value.value == pytest.approx(0.49)
    assert stored.value.input_ids == bad.value.input_ids


def test_recompute_fills_a_missing_value() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    g = graph(opp("customer_value_delivered", None, inputs), *inputs)
    fixed = g.with_recomputed(FormulaValidator().recompute(g))
    assert FormulaValidator().check(fixed) == []


def test_recompute_never_touches_a_field_with_any_other_violation() -> None:
    bad_unit = [rating("importance", 10, "percent"), rating("satisfaction", 5, "percent")]
    unknown = Claim.make(
        text="x",
        tier=Tier.T3,
        confidence=Computed(value=0.5, formula_id="made.up.v1", input_ids=[]),
        **ENV,
    )
    g = graph(opp("ulwick_opportunity", 99, bad_unit), unknown, *bad_unit)
    assert FormulaValidator().recompute(g) == {}


def test_recompute_leaves_a_correct_graph_alone() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    assert (
        FormulaValidator().recompute(graph(opp("customer_value_delivered", 0.49, inputs), *inputs))
        == {}
    )


# -- review fixes ----------------------------------------------------------------


def _custom(fn: object) -> Registry:
    reg = Registry()
    reg.register(
        Formula(
            id="custom",
            fn=fn,  # type: ignore[arg-type]
            slots=(
                InputSlot(
                    name="x",
                    node_type="rating",
                    field="value",
                    units=frozenset({"fraction"}),
                    where={"dimension": "importance"},
                ),
            ),
            target_unit="fraction",
            citation="p. 0",
            construct="probative",
        )
    )
    return reg


def test_a_non_finite_formula_result_never_passes() -> None:
    r = rating("importance", 0.25, "fraction")
    for bad in (float("nan"), float("inf")):
        v = FormulaValidator(_custom(lambda _x, bad=bad: bad)).check(
            graph(opp("custom", 0.3, [r]), r)
        )
        assert codes(v) == ["I4_INPUT_RANGE"]


def test_a_huge_stored_integer_is_a_violation_not_a_crash() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    g = graph(opp("customer_value_delivered", 10**400, inputs), *inputs)  # type: ignore[arg-type]
    assert codes(FormulaValidator().check(g)) == ["I4_VALUE_TYPE"]
    assert FormulaValidator().recompute(g)  # fixable, not a crash


def test_a_huge_input_integer_is_a_violation_not_a_crash() -> None:
    inputs = [rating("importance", 10**400, "fraction"), rating("satisfaction", 0.7, "fraction")]
    assert codes(check(opp("customer_value_delivered", 0.0, inputs), *inputs)) == ["I4_INPUT_RANGE"]


@pytest.mark.parametrize(
    ("unit", "high"), [("scale_0_10", 11), ("percent", 101), ("fraction", 1.5)]
)
def test_gap_inputs_are_range_checked_by_unit(unit: str, high: float) -> None:
    inputs = [rating("importance", high, unit), rating("satisfaction", 0, unit)]
    assert codes(check(opp("gap", high, inputs), *inputs)) == ["I4_INPUT_RANGE"]


def test_the_tolerance_edge_is_1e_9() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    assert check(opp("customer_value_delivered", 0.49 + 1e-10, inputs), *inputs) == []
    assert codes(check(opp("customer_value_delivered", 0.49 + 1e-8, inputs), *inputs)) == [
        "I4_VALUE_MISMATCH"
    ]


def test_recompute_leaves_a_correct_field_when_another_on_the_node_is_wrong() -> None:
    inputs = [rating("importance", 0.7, "fraction"), rating("satisfaction", 0.7, "fraction")]
    g = graph(opp("customer_value_delivered", 0.49, inputs), *inputs)
    assert FormulaValidator().recompute(g) == {}


def test_the_slot_names_follow_the_spec() -> None:
    from probative.formulas.registry import REGISTRY

    slots = REGISTRY.get("customer_value_created").slots
    assert slots is not None
    assert [s.name for s in slots] == ["importance", "satisfaction_after", "satisfaction_before"]
