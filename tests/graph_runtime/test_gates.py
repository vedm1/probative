from __future__ import annotations

import pytest
from pydantic import ValidationError

from probative.graph_runtime.gates import GateDecision, GateRejectReason, apply_amend
from probative.graph_runtime.patch import Patch
from probative.graph_runtime.phases import Phase
from tests.graph_runtime._support import good_ratings, hypothesis_with_test, result


def test_accept_takes_no_payload() -> None:
    assert GateDecision(kind="accept").drop_ids == ()
    with pytest.raises(ValidationError):
        GateDecision(kind="accept", reason=GateRejectReason.WRONG_SCOPE)


def test_reject_needs_a_closed_reason() -> None:
    GateDecision(kind="reject", reason=GateRejectReason.NOT_SUPPORTED)
    with pytest.raises(ValidationError):
        GateDecision(kind="reject")
    with pytest.raises(ValidationError):
        GateDecision(kind="reject", reason="because I said so")  # type: ignore[arg-type]


def test_amend_needs_ids() -> None:
    with pytest.raises(ValidationError):
        GateDecision(kind="amend")


def test_no_free_text_slot_exists_on_a_decision() -> None:
    """I6: a human decides; they never type. Every field is a closed type."""
    for name, field in GateDecision.model_fields.items():
        text = str(field.annotation)
        assert "str]" not in text.replace("Ref", "") or name == "drop_ids", name
    assert set(GateDecision.model_fields) == {"kind", "reason", "drop_ids"}


def test_amend_drops_nodes_and_every_edge_touching_them() -> None:
    nodes, edges = hypothesis_with_test()
    patch = Patch.build("a", Phase.P5, 1, result([*nodes, *good_ratings()], edges))
    hypothesis = nodes[0]
    amended = apply_amend(patch, (hypothesis.id,))
    ids = {n.id for n in amended.result.proposed_nodes}
    assert hypothesis.id not in ids
    assert amended.result.proposed_edges == ()
    assert amended.id != patch.id and amended.cycle == patch.cycle


def test_amend_with_an_unknown_id_is_an_error() -> None:
    patch = Patch.build("a", Phase.P3, 1, result(list(good_ratings())))
    with pytest.raises(ValueError, match="not in the patch"):
        apply_amend(patch, ("rating_000000000000",))


def test_amend_cannot_empty_a_patch() -> None:
    patch = Patch.build("a", Phase.P3, 1, result(list(good_ratings())))
    with pytest.raises(ValueError, match="empty"):
        apply_amend(patch, tuple(n.id for n in patch.result.proposed_nodes))
