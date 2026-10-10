from __future__ import annotations

import types
import typing
from datetime import timedelta

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from probative.core.graph.nodes import NODE_CLASSES, Claim, EvidenceSpan, Need, Node, NodeBase
from probative.core.graph.values import Computed, Input
from tests.core.graph._samples import ENV, all_samples, sample_claim, sample_source

NODE_ADAPTER = TypeAdapter(Node)


def test_there_is_a_node_class_for_every_type_in_design_6_1_plus_partition() -> None:
    # DESIGN §6.1 lists 42 types; CLAIMED_BY targets a Partition §6.1 omits (43)
    assert len(NODE_CLASSES) == 43
    assert set(all_samples()) == set(NODE_CLASSES)


@pytest.mark.parametrize("type_name", sorted(NODE_CLASSES))
def test_every_type_round_trips_through_json(type_name: str) -> None:
    node = all_samples()[type_name]
    again = NODE_ADAPTER.validate_json(NODE_ADAPTER.dump_json(node))
    assert again == node
    assert type(again) is type(node)


@pytest.mark.parametrize("type_name", sorted(NODE_CLASSES))
def test_every_node_carries_partition_and_owner(type_name: str) -> None:
    node = all_samples()[type_name]
    assert node.partition == "main"
    assert node.owner == "ved"
    with pytest.raises(ValidationError):
        type(node).model_validate({**node.model_dump(), "owner": None})


def test_id_is_derived_from_content_and_stable() -> None:
    a, b = sample_claim(), sample_claim()
    assert a.id == b.id
    assert a.id.startswith("claim_") and len(a.id) == len("claim_") + 12
    assert sample_claim("Different").id != a.id


def test_id_ignores_asserted_at_but_not_partition() -> None:
    a = Need.make(text="Reduce time", **ENV)
    later = Need.make(
        text="Reduce time", owner="ved", asserted_at=ENV["asserted_at"] + timedelta(days=1)
    )
    other = Need.make(text="Reduce time", partition="claims", **ENV)
    assert a.id == later.id
    assert a.id != other.id


def test_a_wrong_id_is_rejected() -> None:
    data = sample_claim().model_dump()
    data["id"] = "claim_000000000000"
    with pytest.raises(ValidationError, match="derived"):
        Claim.model_validate(data)


def test_extra_fields_are_rejected() -> None:
    data = sample_claim().model_dump()
    data["surprise"] = 1
    with pytest.raises(ValidationError):
        Claim.model_validate(data)


def test_nodes_are_frozen() -> None:
    with pytest.raises(ValidationError):
        sample_claim().text = "x"  # type: ignore[misc]


def test_span_identity_is_its_whole_content() -> None:
    src = sample_source()
    kw = dict(source_ref=src.id, start=0, end=5, text="hello", **ENV)
    a = EvidenceSpan.make(locator={"line": 1}, **kw)
    assert a.id == EvidenceSpan.make(locator={"line": 1}, **kw).id
    assert a.id != EvidenceSpan.make(locator={"line": 2}, **kw).id


def test_span_text_must_match_its_offsets_length() -> None:
    with pytest.raises(ValidationError):
        EvidenceSpan.make(
            source_ref=sample_source().id, start=0, end=9, text="hello", locator={}, **ENV
        )


def test_source_path_is_relative_and_inside_the_run() -> None:
    base = sample_source().model_dump()
    for bad in ("/abs/notes.md", "../notes.md", "a/../../b.md", "C:\\x.md"):
        with pytest.raises(ValidationError):
            type(sample_source()).model_validate({**base, "path": bad})


def test_source_carries_no_text() -> None:
    assert "text" not in type(sample_source()).model_fields


def test_a_hand_set_confidence_is_unrepresentable() -> None:
    with pytest.raises(ValidationError):
        Claim.make(text="x", tier="T1", confidence=0.9, **ENV)
    with pytest.raises(ValidationError):
        Claim.make(
            text="x", tier="T1", confidence={"value": 0.9, "formula_id": "", "input_ids": []}, **ENV
        )


# --- I4, structural: no bare number on any node ---------------------------

_ALLOWED_BARE = {("EvidenceSpan", "start"), ("EvidenceSpan", "end")}


def _bare_numbers(annotation: object) -> bool:
    if annotation in (int, float):
        return True
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return False  # a nested model is checked on its own terms (Input/Computed/Locator)
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _bare_numbers(typing.get_args(annotation)[0])
    if origin in (typing.Union, types.UnionType, list, dict, tuple, set, frozenset):
        return any(_bare_numbers(a) for a in typing.get_args(annotation))
    return False


def test_no_node_has_a_bare_numeric_field() -> None:
    offenders = [
        f"{cls.__name__}.{name}"
        for cls in NODE_CLASSES.values()
        for name, field in cls.model_fields.items()
        if _bare_numbers(field.annotation) and (cls.__name__, name) not in _ALLOWED_BARE
    ]
    assert offenders == []


def test_the_structural_check_catches_a_seeded_bare_number() -> None:
    class Bad(NodeBase):
        score: float

    assert _bare_numbers(Bad.model_fields["score"].annotation)


def test_numeric_wrappers_are_the_only_numeric_carriers() -> None:
    # Input/Computed are what Rating/Opportunity use for their numbers
    assert NODE_CLASSES["rating"].model_fields["value"].annotation is Input
    assert NODE_CLASSES["opportunity"].model_fields["value"].annotation is Computed
