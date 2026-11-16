"""`FormulaValidator`: recompute every `Computed` value and diff it (I4).

An LLM may propose formula *inputs*. It may never produce an *output*. This is
the check that makes that true on commit: every `Computed` field names a
registered formula, reads the inputs the formula's slots say it reads, and
stores exactly what the formula returns.

It reads each input's *stored* value, not a recomputed one, so one bad value
gives one violation and not a cascade. A field with a dangling input is left to
`validate_graph` (`I4_DANGLING_INPUT`).

`recompute` returns corrected `Computed` values for `Graph.with_recomputed`.
It touches only fields whose inputs are all valid and whose stored value is
missing or wrong; a field with any other violation is never rewritten.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from probative.core.graph.graph import Graph
from probative.core.graph.nodes import NodeBase
from probative.core.graph.validators import Violation
from probative.core.graph.values import Computed, Input
from probative.formulas.registry import (
    FIELD_BINDINGS,
    FRACTION,
    PERCENT,
    REGISTRY,
    UNIT_RANGE,
    Formula,
    FormulaError,
    FormulaInputError,
    InputSlot,
    Pending,
    Registry,
    UnknownFormulaError,
    Unreadable,
)

_FIXABLE = frozenset({"I4_VALUE_MISMATCH", "I4_VALUE_TYPE"})


class RecomputeDivergedError(FormulaError):
    """`settle` did not reach a fixed point (`I4_RECOMPUTE_DIVERGED`)."""


@dataclass(frozen=True)
class _Outcome:
    violations: tuple[Violation, ...] = ()
    result: float | None = None  # set when the inputs were valid and the formula ran


def _computed_fields(node: NodeBase) -> list[tuple[str, Computed]]:
    return [
        (name, value)
        for name in type(node).model_fields
        if isinstance(value := getattr(node, name), Computed)
    ]


class FormulaValidator:
    def __init__(self, registry: Registry = REGISTRY) -> None:
        self._registry = registry

    def check(self, graph: Graph) -> list[Violation]:
        found = [
            v
            for node in graph.nodes.values()
            for name, computed in _computed_fields(node)
            for v in self._evaluate(graph, node, name, computed).violations
        ]
        return sorted(found, key=lambda v: (v.invariant, v.code, v.node_id, v.message))

    def recompute(self, graph: Graph) -> dict[str, dict[str, Computed]]:
        fixes: dict[str, dict[str, Computed]] = {}
        for node in graph.nodes.values():
            for name, computed in _computed_fields(node):
                outcome = self._evaluate(graph, node, name, computed)
                if (
                    outcome.result is not None
                    and outcome.violations
                    and {v.code for v in outcome.violations} <= _FIXABLE
                ):
                    fixes.setdefault(node.id, {})[name] = Computed(
                        value=outcome.result,
                        formula_id=computed.formula_id,
                        input_ids=computed.input_ids,
                    )
        return fixes

    def settle(self, graph: Graph) -> Graph:
        """`recompute` and `Graph.with_recomputed` until nothing is left to fix.

        A value that reads another stored value (a derived claim reads its
        parents) cannot be computed until that one is, so a chain of depth d
        needs d rounds. Each round re-evaluates every field, so a parent
        corrected in round k corrects its child in round k + 1. The bound is the
        node count; hitting it is `I4_RECOMPUTE_DIVERGED`, never a silent stop.
        What `settle` cannot fix stays for `check` to report."""
        for _ in range(len(graph.nodes) + 2):
            fixes = self.recompute(graph)
            if not fixes:
                return graph
            graph = graph.with_recomputed(fixes)
        raise RecomputeDivergedError("I4_RECOMPUTE_DIVERGED: recomputing did not settle")

    # -- one field ---------------------------------------------------------------

    def _evaluate(self, graph: Graph, node: NodeBase, name: str, computed: Computed) -> _Outcome:
        def fail(code: str, message: str) -> Violation:
            return Violation("I4", code, node.id, f"{name}: {message}")

        if any(ref not in graph.nodes for ref in computed.input_ids):
            return _Outcome()
        try:
            formula = self._registry.get(computed.formula_id)
        except UnknownFormulaError:
            return _Outcome(
                (fail("I4_UNKNOWN_FORMULA", f"{computed.formula_id!r} is not registered"),)
            )
        allowed = FIELD_BINDINGS.get((str(getattr(node, "type", "")), name))
        if allowed is not None and formula.id not in allowed:
            return _Outcome(
                (
                    fail(
                        "I4_FORMULA_BINDING",
                        f"{formula.id} may not fill this field; it takes {sorted(allowed)}",
                    ),
                )
            )
        if formula.fact is not None:
            return self._evaluate_fact(graph, node, formula, computed, fail)
        if formula.slots is None:
            return _Outcome(
                (fail("I4_UNBOUND_FORMULA", f"{formula.id} is not yet bound to graph nodes"),)
            )
        if len(computed.input_ids) != len(formula.slots):
            return _Outcome(
                (
                    fail(
                        "I4_INPUT_ARITY",
                        f"{formula.id} takes {len(formula.slots)} inputs, "
                        f"got {len(computed.input_ids)}",
                    ),
                )
            )

        values: list[float] = []
        problems: list[Violation] = []
        units: list[str] = []
        for slot, ref in zip(formula.slots, computed.input_ids, strict=True):
            read = _read(graph.nodes[ref], slot)
            if isinstance(read, str):
                problems.append(fail("I4_INPUT_TYPE", f"{slot.name} ({ref}): {read}"))
                continue
            if read.unit not in slot.units:
                problems.append(
                    fail(
                        "I4_INPUT_UNIT",
                        f"{slot.name} ({ref}) is in {read.unit!r}; {formula.id} accepts "
                        f"{sorted(slot.units)}",
                    )
                )
                continue
            try:
                number = float(read.value)
            except OverflowError:
                number = math.inf
            low, high = UNIT_RANGE.get(read.unit, (-math.inf, math.inf))
            if not low <= number <= high:
                problems.append(
                    fail(
                        "I4_INPUT_RANGE",
                        f"{slot.name} ({ref}) is outside {low:g} to {high:g} for {read.unit!r}",
                    )
                )
                continue
            units.append(read.unit)
            values.append(number)
            if formula.target_unit == FRACTION and read.unit == PERCENT:
                values[-1] /= 100
        if not problems and formula.target_unit is None and len(set(units)) > 1:
            problems.append(
                fail(
                    "I4_INPUT_UNIT",
                    f"{formula.id} needs one unit for every input, got {sorted(set(units))}",
                )
            )
        if problems:
            return _Outcome(tuple(problems))

        try:
            result = float(formula.fn(*values))
        except FormulaInputError as err:
            return _Outcome((fail("I4_INPUT_RANGE", str(err)),))
        if not math.isfinite(result):
            return _Outcome((fail("I4_INPUT_RANGE", f"{formula.id} gave {result!r}"),))
        return self._diff(fail, formula, computed, result)

    def _evaluate_fact(
        self,
        graph: Graph,
        node: NodeBase,
        formula: Formula,
        computed: Computed,
        fail: Callable[[str, str], Violation],
    ) -> _Outcome:
        """A formula that reads graph structure (PB13). It reads the node that owns
        the `Computed` and no other, so a claim cannot borrow another claim's number."""
        assert formula.fact is not None
        if len(computed.input_ids) != 1:
            return _Outcome(
                (
                    fail(
                        "I4_INPUT_ARITY",
                        f"{formula.id} takes 1 input, got {len(computed.input_ids)}",
                    ),
                )
            )
        if computed.input_ids[0] != node.id:
            return _Outcome(
                (
                    fail(
                        "I4_INPUT_TYPE",
                        f"{formula.id} reads its own node, not {computed.input_ids[0]}",
                    ),
                )
            )
        read = formula.fact.fn(graph, node.id)
        if isinstance(read, Unreadable):
            return _Outcome((fail("I4_INPUT_TYPE", read.reason),))
        if isinstance(read, Pending):
            return _Outcome((fail("I4_INPUT_PENDING", read.reason),))
        try:
            result = float(formula.fn(*read))
        except FormulaInputError as err:
            return _Outcome((fail("I4_INPUT_RANGE", str(err)),))
        if not math.isfinite(result):
            return _Outcome((fail("I4_INPUT_RANGE", f"{formula.id} gave {result!r}"),))
        return self._diff(fail, formula, computed, result)

    @staticmethod
    def _diff(
        fail: Callable[[str, str], Violation], formula: Formula, computed: Computed, result: float
    ) -> _Outcome:
        stored = computed.value
        try:
            usable = (
                stored is not None
                and not isinstance(stored, bool)
                and isinstance(stored, int | float)
                and math.isfinite(stored)
            )
            number = float(stored) if usable else 0.0  # type: ignore[arg-type]
        except OverflowError:
            usable, number = False, 0.0
        if not usable:
            return _Outcome(
                (fail("I4_VALUE_TYPE", f"stored value is not a usable number ({_short(stored)})"),),
                result,
            )
        if not abs(number - result) <= formula.tolerance:
            return _Outcome(
                (
                    fail(
                        "I4_VALUE_MISMATCH",
                        f"{formula.id} gives {result:.12g}, stored {number:.12g}",
                    ),
                ),
                result,
            )
        return _Outcome((), result)


def _short(value: object) -> str:
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _read(node: NodeBase, slot: InputSlot) -> Input | str:
    """The `Input` a slot names on `node`, or why it is not one."""
    kind = getattr(node, "type", None)
    if kind != slot.node_type:
        return f"is a {kind!r} node, expected {slot.node_type!r}"
    for key, want in slot.where.items():
        if str(getattr(getattr(node, key, None), "value", getattr(node, key, None))) != want:
            return f"has {key}={getattr(node, key, None)!r}, expected {want!r}"
    value = getattr(node, slot.field, None)
    if not isinstance(value, Input):
        return f"field {slot.field!r} is not an Input"
    return value
