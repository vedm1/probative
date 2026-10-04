"""PB6-p2: the opt-in segment extraction pass. The default passes are
untouched (PB4's recordings are keyed by prompt hash), segments come only when
a caller asks, and a segment quote resolves exactly like any other."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from probative.core.candidates import CandidateKind, RejectReason
from probative.extract import extract_candidates
from probative.extract.prompts import (
    CONSTRAINT_PROMPT,
    GENERAL_PROMPT,
    PASSES,
    SEGMENT_PASS,
    ConstraintOutput,
    GeneralOutput,
    RawQuote,
    SegmentOutput,
)
from probative.llm import FakeProvider, Message, StructuredResult, TokenUsage
from tests.extract._helpers import make_source

TEXT = (
    "# Billing PRD\n"
    "Our target customers are adults aged 30 to 50 with a household income above $80,000.\n"
    "Our target is freelancers. They invoice many clients and chase late payment weekly.\n"
    "As a freelancer I want reminders so that I get paid on time.\n"
)
BUCKET = "Our target customers are adults aged 30 to 50 with a household income above $80,000."
TWO_SENTENCES = (
    "Our target is freelancers. They invoice many clients and chase late payment weekly."
)
STORY = "As a freelancer I want reminders so that I get paid on time."


def _seg(*quotes: str) -> SegmentOutput:
    return SegmentOutput(segments=[RawQuote(quote=q) for q in quotes])


def test_default_prompts_are_byte_identical_to_pb4s() -> None:
    """PB4's recordings are keyed by sha256(messages). Editing either prompt
    would make every PB4 recording miss, so the hashes are pinned."""
    assert (
        hashlib.sha256(GENERAL_PROMPT.encode()).hexdigest()
        == "a5b2b3a95e5107d5d7081d0a163cc862eb157e333021f6cb15cc0b791c2b59af"
    )
    assert (
        hashlib.sha256(CONSTRAINT_PROMPT.encode()).hexdigest()
        == "8c556df766b710dbe61c26290b08fdada4d4d94b10cf858cf0552433a9c39542"
    )
    assert [p.name for p in PASSES] == ["general", "constraint"]
    assert SEGMENT_PASS not in PASSES


class _Calls:
    def __init__(self, outputs: list[Any]) -> None:
        self.inner = FakeProvider(outputs, usage=TokenUsage(input_tokens=10, output_tokens=2))
        self.calls: list[list[Message]] = []

    def complete_structured(
        self, messages: list[Message], *, output_model: type[Any], model: str
    ) -> StructuredResult[Any]:
        self.calls.append(messages)
        return self.inner.complete_structured(messages, output_model=output_model, model=model)


def test_segments_are_not_asked_for_by_default() -> None:
    provider = _Calls([GeneralOutput(), ConstraintOutput()])
    result = extract_candidates(make_source(TEXT), provider, model="m")
    assert len(provider.calls) == 2
    assert result.segments == []


def test_opt_in_pass_yields_located_segments() -> None:
    source = make_source(TEXT)
    provider = _Calls([GeneralOutput(), ConstraintOutput(), _seg(BUCKET, TWO_SENTENCES)])
    result = extract_candidates(source, provider, model="m", passes=[*PASSES, SEGMENT_PASS])
    assert len(provider.calls) == 3
    assert [c.text for c in result.segments] == [BUCKET, TWO_SENTENCES]
    assert all(c.kind is CandidateKind.SEGMENT for c in result.segments)
    for segment in result.segments:
        ev = segment.evidence  # sliced from the source, never from the model (I1)
        assert source.text[ev.start : ev.end] == ev.text
    assert result.usage == TokenUsage(input_tokens=30, output_tokens=6)


def test_segment_pass_alone_makes_one_call() -> None:
    provider = _Calls([_seg(BUCKET)])
    result = extract_candidates(make_source(TEXT), provider, model="m", passes=[SEGMENT_PASS])
    assert len(provider.calls) == 1
    assert len(result.segments) == 1
    assert result.claims == result.needs == result.stories == []


def test_a_segment_the_document_does_not_contain_is_rejected_not_believed() -> None:
    provider = _Calls([_seg("Our target is small banks in Europe.", BUCKET)])
    result = extract_candidates(make_source(TEXT), provider, model="m", passes=[SEGMENT_PASS])
    assert [c.text for c in result.segments] == [BUCKET]
    assert [(r.kind, r.reason) for r in result.rejected] == [
        (CandidateKind.SEGMENT, RejectReason.NOT_FOUND)
    ]


def test_a_segment_quote_over_the_cap_is_rejected() -> None:
    provider = _Calls([_seg(TWO_SENTENCES)])
    result = extract_candidates(
        make_source(TEXT), provider, model="m", passes=[SEGMENT_PASS], max_quote_chars=40
    )
    assert result.segments == []
    assert result.rejected[0].reason is RejectReason.TOO_LONG


def test_an_empty_passes_list_is_an_error_not_a_silent_no_op() -> None:
    with pytest.raises(ValueError, match="passes"):
        extract_candidates(make_source(TEXT), _Calls([]), model="m", passes=[])


def test_the_segment_prompt_keeps_buckets_and_excludes_stories() -> None:
    prompt = SEGMENT_PASS.system_prompt.lower()
    assert "<document>" in prompt and "data" in prompt
    # The critic must get to see a demographic bucket: never filter it out here.
    assert "do not exclude" in prompt or "even if" in prompt
    assert "demographic" in prompt or "who they are" in prompt
    assert "story" in prompt  # "As a ... I want" is not a segment definition
    assert "own knowledge" in prompt  # never add a segment the document does not state
    assert STORY not in SEGMENT_PASS.system_prompt  # no fixture text in the prompt


def test_segment_output_model_has_no_room_for_a_score() -> None:
    assert set(SegmentOutput.model_fields) == {"segments"}
    assert set(RawQuote.model_fields) == {"quote"}
