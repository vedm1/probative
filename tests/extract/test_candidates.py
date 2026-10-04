"""PB4 types (core/candidates.py): a candidate with no locator is
unconstructible (I1), ids are derived not authored, and no candidate carries
a number a model could have invented (I4)."""

from __future__ import annotations

from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from probative.core.candidates import (
    Candidate,
    CandidateKind,
    ClaimCandidate,
    ConstraintCandidate,
    DependencyCandidate,
    ExtractionResult,
    NeedCandidate,
    RejectedQuote,
    RejectReason,
    SegmentCandidate,
    StoryCandidate,
    candidate_id,
)
from probative.core.evidence import EvidenceSpan, Locator
from probative.llm.types import TokenUsage


def _span(start: int = 0, end: int = 5, text: str = "hello") -> EvidenceSpan:
    return EvidenceSpan(source_id="src_a", start=start, end=end, text=text, locator=Locator())


def _need(span: EvidenceSpan | None = None) -> NeedCandidate:
    span = span or _span()
    return NeedCandidate(id=candidate_id(CandidateKind.NEED, span), evidence=span)


def test_candidate_without_evidence_is_unconstructible() -> None:
    with pytest.raises(ValidationError):
        NeedCandidate.model_validate({"id": "cand_need_x"})


def test_candidate_with_null_evidence_is_unconstructible() -> None:
    with pytest.raises(ValidationError):
        NeedCandidate.model_validate({"id": "cand_need_x", "evidence": None})


def test_id_is_deterministic_and_kind_scoped() -> None:
    span = _span()
    assert candidate_id(CandidateKind.NEED, span) == candidate_id(CandidateKind.NEED, span)
    assert candidate_id(CandidateKind.NEED, span) != candidate_id(CandidateKind.CLAIM, span)
    assert candidate_id(CandidateKind.NEED, span).startswith("cand_need_")
    assert candidate_id(CandidateKind.NEED, _span(0, 5)) != candidate_id(
        CandidateKind.NEED, _span(1, 6)
    )


def test_hand_set_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="id"):
        NeedCandidate(id="cand_need_handwritten", evidence=_span())


def test_text_is_the_evidence_text_not_a_second_copy() -> None:
    assert _need().text == "hello"
    assert "text" not in NeedCandidate.model_fields


def test_candidate_is_frozen() -> None:
    need = _need()
    with pytest.raises(ValidationError):
        need.evidence = _span(1, 6, "ello ")  # type: ignore[misc]


@pytest.mark.parametrize(
    ("cls", "kind"),
    [
        (ClaimCandidate, CandidateKind.CLAIM),
        (NeedCandidate, CandidateKind.NEED),
        (StoryCandidate, CandidateKind.STORY),
        (ConstraintCandidate, CandidateKind.CONSTRAINT),
        (DependencyCandidate, CandidateKind.DEPENDENCY),
        (SegmentCandidate, CandidateKind.SEGMENT),
    ],
)
def test_each_class_has_its_kind_by_default(cls: type[Any], kind: CandidateKind) -> None:
    span = _span()
    candidate = cls(id=candidate_id(kind, span), evidence=span)
    assert candidate.kind is kind


def test_discriminated_union_roundtrips_through_json() -> None:
    adapter: TypeAdapter[Candidate] = TypeAdapter(Candidate)
    span = _span()
    original = ConstraintCandidate(id=candidate_id(CandidateKind.CONSTRAINT, span), evidence=span)
    restored = adapter.validate_json(adapter.dump_json(original))
    assert restored == original
    assert isinstance(restored, ConstraintCandidate)


def _numeric_annotations(model: type[BaseModel], seen: set[type]) -> list[str]:
    """Names of every int/float-typed field reachable from `model`."""
    found: list[str] = []
    seen.add(model)
    for name, field in model.model_fields.items():
        stack = [field.annotation]
        while stack:
            ann = stack.pop()
            if ann in (int, float):
                found.append(f"{model.__name__}.{name}")
            elif isinstance(ann, type) and issubclass(ann, BaseModel) and ann not in seen:
                found.extend(_numeric_annotations(ann, seen))
            elif get_origin(ann) is not None:
                stack.extend(get_args(ann))
    return found


def test_no_candidate_carries_a_number_except_position_integers() -> None:
    """I4: nothing a model could author a score into. The only numbers
    reachable from a candidate are structural positions in the source:
    character offsets and the locator's page/line."""
    for cls in (
        ClaimCandidate,
        NeedCandidate,
        StoryCandidate,
        ConstraintCandidate,
        DependencyCandidate,
        SegmentCandidate,
    ):
        assert sorted(_numeric_annotations(cls, set())) == [
            "EvidenceSpan.end",
            "EvidenceSpan.start",
            "Locator.line",
            "Locator.page",
        ], cls.__name__


def test_extraction_result_flattens_in_document_order() -> None:
    first, second, third = _span(0, 5), _span(10, 15), _span(20, 25)
    result = ExtractionResult(
        source_id="src_a",
        claims=[
            ClaimCandidate(id=candidate_id(CandidateKind.CLAIM, third), evidence=third),
        ],
        needs=[
            NeedCandidate(id=candidate_id(CandidateKind.NEED, first), evidence=first),
        ],
        stories=[
            StoryCandidate(id=candidate_id(CandidateKind.STORY, second), evidence=second),
        ],
        rejected=[
            RejectedQuote(kind=CandidateKind.NEED, quote="nope", reason=RejectReason.NOT_FOUND)
        ],
        usage=TokenUsage(input_tokens=3, output_tokens=4),
    )
    assert [c.evidence.start for c in result.candidates()] == [0, 10, 20]
    assert result.usage.total_tokens == 7


def test_candidate_rejects_an_incoherent_span() -> None:
    inverted = EvidenceSpan(source_id="s", start=5, end=2, text="hello", locator=Locator())
    wrong_length = EvidenceSpan(source_id="s", start=0, end=9, text="hello", locator=Locator())
    for bad in (inverted, wrong_length):
        with pytest.raises(ValidationError, match="span"):
            NeedCandidate(id=candidate_id(CandidateKind.NEED, bad), evidence=bad)


def test_segment_candidate_id_is_derived_and_prefixed() -> None:
    span = _span()
    candidate = SegmentCandidate(id=candidate_id(CandidateKind.SEGMENT, span), evidence=span)
    assert candidate.id.startswith("cand_segment_")
    assert candidate.text == "hello"
    with pytest.raises(ValidationError, match="derived id"):
        SegmentCandidate(id="cand_segment_handwritten", evidence=span)


def test_segment_candidate_is_in_the_union_and_the_result() -> None:
    adapter: TypeAdapter[Candidate] = TypeAdapter(Candidate)
    first, second = _span(0, 5), _span(10, 15)
    segment = SegmentCandidate(id=candidate_id(CandidateKind.SEGMENT, second), evidence=second)
    assert adapter.validate_json(adapter.dump_json(segment)) == segment
    result = ExtractionResult(
        source_id="src_a",
        needs=[NeedCandidate(id=candidate_id(CandidateKind.NEED, first), evidence=first)],
        segments=[segment],
    )
    assert [c.kind for c in result.candidates()] == [CandidateKind.NEED, CandidateKind.SEGMENT]
    assert ExtractionResult(source_id="src_a").segments == []
