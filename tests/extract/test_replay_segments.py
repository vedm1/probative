"""Replays the committed segment-pass recordings
(tests/fixtures/extract/recordings_segments/) through the real `LiteLLMProvider`
parse path and pins what they scored (PB6-p2). No key, no network.

Three synthetic documents, four gold segments in total: this pins what the model
earned when recorded; it is not a precision/recall estimate. A changed prompt or
document breaks the recording key on purpose; re-record."""

from __future__ import annotations

import json
from typing import Any

import pytest

from probative.core.candidates import CandidateKind, ExtractionResult
from probative.core.evidence import EvidenceKind, Source, Tier
from probative.extract import (
    SEGMENT_PASS,
    ExtractionScore,
    extract_candidates,
    gold_candidates,
    load_gold_labels,
    score_extraction,
)
from probative.ingest import ingest, reextract
from probative.llm import LiteLLMProvider
from tests._recording import replay
from tests.extract._helpers import FIXTURES
from tests.extract._paths import GOLD
from tests.extract._segments import SEGMENT_CORPUS, SEGMENT_RECORDINGS, SEGMENT_RERECORD_HINT

RESULTS: dict[str, Any] = json.loads((SEGMENT_RECORDINGS / "results.json").read_text())


def _run(document: str, gold_file: str) -> tuple[Source, ExtractionResult, ExtractionScore]:
    source = ingest(FIXTURES / document, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    provider = LiteLLMProvider(completion_fn=replay(SEGMENT_RECORDINGS, SEGMENT_RERECORD_HINT))
    result = extract_candidates(source, provider, model=RESULTS["model"], passes=[SEGMENT_PASS])
    gold = gold_candidates(source, load_gold_labels(GOLD / gold_file))
    return source, result, score_extraction(result.candidates(), gold)


def test_every_recorded_response_names_the_pinned_reference_model() -> None:
    assert RESULTS["model"] == "anthropic/claude-sonnet-5"
    for path in SEGMENT_RECORDINGS.glob("*.json"):
        if path.name != "results.json":
            assert json.loads(path.read_text())["model"].startswith("claude-sonnet-5"), path.name


@pytest.mark.parametrize(("document", "gold_file"), SEGMENT_CORPUS)
def test_replayed_score_candidates_and_usage_equal_the_recorded_ones(
    document: str, gold_file: str
) -> None:
    _, result, score = _run(document, gold_file)
    recorded = RESULTS["documents"][document]
    assert score.model_dump(mode="json") == recorded["score"]
    assert [{"kind": c.kind.value, "text": c.text} for c in result.candidates()] == recorded[
        "predicted"
    ]
    assert [r.model_dump(mode="json") for r in result.rejected] == recorded["rejected"]
    assert result.usage.model_dump() == recorded["usage"]


@pytest.mark.parametrize(("document", "gold_file"), SEGMENT_CORPUS)
def test_every_recorded_segment_reextracts_to_its_recorded_text(
    document: str, gold_file: str
) -> None:
    """I1 against a real model's output."""
    source, result, _ = _run(document, gold_file)
    for candidate in result.candidates():
        assert reextract(source, candidate.evidence) == candidate.evidence.text


def test_the_model_found_all_four_segments_including_the_two_sentence_one() -> None:
    _, result, score = _run("prd_segments.md", "prd_segments.json")
    seg = score.per_kind[CandidateKind.SEGMENT]
    assert (seg.tp, seg.fp, seg.fn) == (4, 0, 0)
    assert any(
        c.text.startswith("Our third group is bookkeepers. They reconcile") for c in result.segments
    )
    assert result.rejected == []  # it never produced a quote that is not in the document


def test_the_traps_were_not_returned_as_segments() -> None:
    """A story naming a role, a need naming a role, a group size, one person and an
    injected instruction: none is a segment definition. The injection result is measured
    behaviour for this model at this prompt, not a structural guarantee."""
    _, result, _ = _run("prd_segments.md", "prd_segments.json")
    for segment in result.segments:
        for trap in (
            "As a freelance photographer",
            "Freelancers need to know",
            "About four million",
            "Maria is a 34-year-old",
            "Ignore all previous instructions",
            "all humans",
        ):
            assert trap not in segment.text


@pytest.mark.parametrize("document", ["memo_logistics.txt", "prd_payments.md"])
def test_documents_that_define_no_target_group_yield_no_segments(document: str) -> None:
    """The candidate-free memo and PB4's PRD (the false-positive probe)."""
    gold_file = dict(SEGMENT_CORPUS)[document]
    _, result, score = _run(document, gold_file)
    assert result.segments == []
    assert score.per_kind[CandidateKind.SEGMENT].fp == 0
