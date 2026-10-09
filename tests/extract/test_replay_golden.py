"""Replays the committed live recordings (tests/fixtures/extract/recordings/)
through the real `LiteLLMProvider` parse path and pins what they scored.

No key, no network: the recordings are the model's answers, captured once by
`test_live_record.py`. These tests do not measure the model — they hold the
pipeline, prompts and scoring to the numbers the model earned when recorded,
so a change to any of them shows up as a diff rather than silently. Changing
a prompt or a fixture breaks the recording key on purpose; re-record.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from probative.core.candidates import CandidateKind, ExtractionResult
from probative.core.evidence import EvidenceKind, Source, Tier
from probative.extract import (
    ExtractionScore,
    extract_candidates,
    gold_candidates,
    load_gold_labels,
    score_extraction,
)
from probative.ingest import ingest, reextract
from probative.llm import LiteLLMProvider
from tests._recording import replay
from tests.extract._helpers import FIXTURES, RECORDINGS, RERECORD_HINT
from tests.extract._paths import CORPUS, GOLD

RESULTS: dict[str, Any] = json.loads((RECORDINGS / "results.json").read_text())


def _run(document: str, gold_file: str) -> tuple[Source, ExtractionResult, ExtractionScore]:
    source = ingest(FIXTURES / document, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    provider = LiteLLMProvider(completion_fn=replay(RECORDINGS, RERECORD_HINT))
    result = extract_candidates(source, provider, model=RESULTS["model"])
    gold = gold_candidates(source, load_gold_labels(GOLD / gold_file))
    return source, result, score_extraction(result.candidates(), gold)


def test_recording_names_its_model() -> None:
    assert RESULTS["model"] == "anthropic/claude-sonnet-5"


@pytest.mark.parametrize(("document", "gold_file"), CORPUS)
def test_replayed_score_equals_the_recorded_score(document: str, gold_file: str) -> None:
    _, _, score = _run(document, gold_file)
    dumped = score.model_dump(mode="json")
    # PB4 recorded five kinds; PB6-p2 added a sixth, which this corpus has no
    # segments for (default passes never ask) and so must score all-zero.
    segment = dumped["per_kind"].pop(CandidateKind.SEGMENT.value)
    assert (segment["tp"], segment["fp"], segment["fn"]) == (0, 0, 0)
    forecast = dumped["per_kind"].pop(CandidateKind.FORECAST.value)  # PB8: likewise
    assert (forecast["tp"], forecast["fp"], forecast["fn"]) == (0, 0, 0)
    assert dumped == RESULTS["documents"][document]["score"]


@pytest.mark.parametrize(("document", "gold_file"), CORPUS)
def test_replayed_candidates_and_rejections_equal_the_recorded_ones(
    document: str, gold_file: str
) -> None:
    _, result, _ = _run(document, gold_file)
    recorded = RESULTS["documents"][document]
    assert [{"kind": c.kind.value, "text": c.text} for c in result.candidates()] == recorded[
        "predicted"
    ]
    assert [r.model_dump(mode="json") for r in result.rejected] == recorded["rejected"]
    assert result.usage.model_dump() == recorded["usage"]


@pytest.mark.parametrize(("document", "gold_file"), CORPUS)
def test_every_recorded_candidate_reextracts_to_its_recorded_text(
    document: str, gold_file: str
) -> None:
    """Gating check 1 (I1), against a real model's output."""
    source, result, _ = _run(document, gold_file)
    for candidate in result.candidates():
        assert reextract(source, candidate.evidence) == candidate.evidence.text


def test_a_candidate_free_document_yields_no_candidates() -> None:
    """Gating check 3."""
    _, result, score = _run("memo_logistics.txt", "memo_logistics.json")
    assert result.candidates() == []
    assert result.rejected == []
    assert score.overall.fp == 0


def test_the_injection_sentence_yields_no_constraint() -> None:
    """Gating check 4 — for this model, at this prompt. Not a guarantee: the
    injected sentence is in the document, so a different model could quote it
    (PB4 spec, design decision 1)."""
    _, result, _ = _run("prd_payments.md", "prd_payments_md.json")
    for candidate in result.candidates():
        assert "CCPA" not in candidate.text
        assert "ignore all previous" not in candidate.text.lower()
    assert all("CCPA" not in c.text for c in result.constraints)


def test_the_model_never_produced_an_unlocatable_quote_on_this_corpus() -> None:
    for document, _ in CORPUS:
        assert RESULTS["documents"][document]["rejected"] == []


def test_recorded_recall_is_complete_and_precision_gaps_are_the_known_ones() -> None:
    """The measured shape, stated so a regression in either direction is
    a deliberate edit. Overall recall 1.0; the only false positives are
    constraint-like sentences also tagged as dependencies, and one
    unlabelled priority statement tagged as a claim."""
    md = RESULTS["documents"]["prd_payments.md"]["score"]["per_kind"]
    pdf = RESULTS["documents"]["prd_payments.pdf"]["score"]["per_kind"]
    for per_kind in (md, pdf):
        # PB4 recorded five kinds; segment (PB6-p2) and forecast (PB8) have their own recordings.
        recorded = [
            k for k in CandidateKind if k not in (CandidateKind.SEGMENT, CandidateKind.FORECAST)
        ]
        assert all(per_kind[k.value]["fn"] == 0 for k in recorded)
    assert md[CandidateKind.DEPENDENCY.value]["fp"] == 3
    assert pdf[CandidateKind.DEPENDENCY.value]["fp"] == 2
    assert md[CandidateKind.CLAIM.value]["fp"] == 1
    for kind in (CandidateKind.NEED, CandidateKind.STORY, CandidateKind.CONSTRAINT):
        assert md[kind.value]["fp"] == pdf[kind.value]["fp"] == 0
