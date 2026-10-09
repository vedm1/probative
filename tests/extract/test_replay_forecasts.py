"""Replays the committed forecast-pass recordings
(tests/fixtures/extract/recordings_forecasts/) through the real `LiteLLMProvider`
parse path and pins what they scored (PB8 checkpoint A). No key, no network.

Pins what the model earned when recorded; it is not a precision/recall estimate.
Every test is skipped until the developer has recorded (a recording is a
developer action, S3). Checkpoint A is not done until these run, not skip."""

from __future__ import annotations

import json
from typing import Any

import pytest

from probative.core.candidates import CandidateKind, ExtractionResult
from probative.core.evidence import EvidenceKind, Source, Tier
from probative.extract import (
    FORECAST_PASS,
    ExtractionScore,
    extract_candidates,
    gold_candidates,
    load_gold_labels,
    score_extraction,
)
from probative.ingest import ingest, reextract
from probative.llm import LiteLLMProvider
from tests._recording import replay
from tests.extract._forecasts import FORECAST_CORPUS, FORECAST_RECORDINGS, FORECAST_RERECORD_HINT
from tests.extract._helpers import FIXTURES
from tests.extract._paths import GOLD

_RESULTS_PATH = FORECAST_RECORDINGS / "results.json"
RECORDED = _RESULTS_PATH.exists()
RESULTS: dict[str, Any] = json.loads(_RESULTS_PATH.read_text()) if RECORDED else {}
needs_recording = pytest.mark.skipif(not RECORDED, reason=FORECAST_RERECORD_HINT)


def _run(document: str, gold_file: str) -> tuple[Source, ExtractionResult, ExtractionScore]:
    source = ingest(FIXTURES / document, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    provider = LiteLLMProvider(completion_fn=replay(FORECAST_RECORDINGS, FORECAST_RERECORD_HINT))
    result = extract_candidates(source, provider, model=RESULTS["model"], passes=[FORECAST_PASS])
    gold = gold_candidates(source, load_gold_labels(GOLD / gold_file))
    return source, result, score_extraction(result.candidates(), gold)


@needs_recording
def test_every_recorded_response_names_the_pinned_reference_model() -> None:
    assert RESULTS["model"] == "anthropic/claude-sonnet-5"
    for path in FORECAST_RECORDINGS.glob("*.json"):
        if path.name != "results.json":
            assert json.loads(path.read_text())["model"].startswith("claude-sonnet-5"), path.name


@needs_recording
@pytest.mark.parametrize(("document", "gold_file"), FORECAST_CORPUS)
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


@needs_recording
@pytest.mark.parametrize(("document", "gold_file"), FORECAST_CORPUS)
def test_every_recorded_forecast_reextracts_to_its_recorded_text(
    document: str, gold_file: str
) -> None:
    """I1 against a real model's output."""
    source, result, _ = _run(document, gold_file)
    for candidate in result.candidates():
        assert reextract(source, candidate.evidence) == candidate.evidence.text


@needs_recording
def test_the_traps_were_not_returned_as_forecasts() -> None:
    """Plan, requirement, target, a present fact containing "will", a story and an
    injected instruction. Injection result is measured behaviour, not a guarantee."""
    from tests.extract.test_forecast_gold import TRAPS

    _, result, _ = _run("prd_forecasts.md", "prd_forecasts.json")
    for forecast in result.forecasts:
        assert not any(trap in forecast.text for trap in TRAPS)


@needs_recording
def test_gold_forecasts_found() -> None:
    _, _, score = _run("prd_forecasts.md", "prd_forecasts.json")
    kind = score.per_kind[CandidateKind.FORECAST]
    assert (kind.tp, kind.fn) == (4, 0)
