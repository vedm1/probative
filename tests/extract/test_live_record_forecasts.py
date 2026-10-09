"""Records real model responses for the PB8 forecast pass and measures it.
Never runs in default CI (`-m live`). A developer action:

    ANTHROPIC_API_KEY=sk-... uv run pytest -m live tests/extract/test_live_record_forecasts.py -s

Deletes and rewrites tests/fixtures/extract/recordings_forecasts/ only (PB4's
recordings are untouched), including `results.json` — the recorded
precision/recall that `test_replay_forecasts.py` pins. Only the forecast pass
runs: the default passes are PB4's and already recorded.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

from probative.config import REFERENCE_MODEL
from probative.core.candidates import CandidateKind
from probative.core.evidence import EvidenceKind, Tier
from probative.extract import (
    FORECAST_PASS,
    extract_candidates,
    gold_candidates,
    load_gold_labels,
    score_extraction,
)
from probative.ingest import ingest
from probative.llm import LiteLLMProvider
from tests._recording import Recorder
from tests.extract._forecasts import FORECAST_CORPUS, FORECAST_RECORDINGS
from tests.extract._helpers import FIXTURES
from tests.extract._paths import GOLD

pytestmark = pytest.mark.live


def test_record_forecast_pass_and_measure() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    real = LiteLLMProvider()._completion()  # this module may not import litellm (TID251)
    staging = FORECAST_RECORDINGS.with_name(f"{FORECAST_RECORDINGS.name}.recording")
    shutil.rmtree(staging, ignore_errors=True)
    provider = LiteLLMProvider(completion_fn=Recorder(real, staging))

    documents: dict[str, object] = {}
    for document, gold_file in FORECAST_CORPUS:
        source = ingest(FIXTURES / document, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
        gold = gold_candidates(source, load_gold_labels(GOLD / gold_file))
        result = extract_candidates(source, provider, model=REFERENCE_MODEL, passes=[FORECAST_PASS])
        score = score_extraction(result.candidates(), gold)
        documents[document] = {
            "score": score.model_dump(mode="json"),
            "rejected": [r.model_dump(mode="json") for r in result.rejected],
            "usage": result.usage.model_dump(),
            "predicted": [{"kind": c.kind.value, "text": c.text} for c in result.candidates()],
        }
        print(f"\n== {document}: forecast {score.per_kind[CandidateKind.FORECAST]}")
        print(f"   predicted: {[c.text for c in result.candidates()]}")
        print(f"   rejected: {[(r.reason.value, r.quote[:50]) for r in result.rejected]}")
    (staging / "results.json").write_text(
        json.dumps({"model": REFERENCE_MODEL, "documents": documents}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(FORECAST_RECORDINGS, ignore_errors=True)
    staging.rename(FORECAST_RECORDINGS)
