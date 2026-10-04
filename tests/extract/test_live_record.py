"""Records real model responses for the PB4 corpus and measures the extractor.
Never runs in default CI (`-m live`). A developer action:

    ANTHROPIC_API_KEY=sk-... uv run pytest -m live tests/extract/test_live_record.py -s

Deletes and rewrites tests/fixtures/extract/recordings/, including
`results.json` — the recorded precision/recall that `test_replay_golden.py`
pins and the PB4 Implementation notes quote.
"""

from __future__ import annotations

import json
import os

import pytest

from probative.config import Settings
from probative.core.candidates import CandidateKind
from probative.core.evidence import EvidenceKind, Tier
from probative.extract import (
    extract_candidates,
    gold_candidates,
    load_gold_labels,
    score_extraction,
)
from probative.ingest import ingest
from probative.llm import LiteLLMProvider
from tests._recording import Recorder
from tests.extract._helpers import FIXTURES, RECORDINGS
from tests.extract._paths import CORPUS, GOLD

pytestmark = pytest.mark.live


def test_record_corpus_and_measure() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    model = os.environ.get("PROBATIVE_MODEL") or Settings().model
    # `_completion()` resolves the real litellm.completion lazily; this module
    # may not import litellm itself (TID251).
    real = LiteLLMProvider()._completion()

    if RECORDINGS.exists():
        for stale in RECORDINGS.glob("*.json"):
            stale.unlink()
    provider = LiteLLMProvider(completion_fn=Recorder(real, RECORDINGS))

    results: dict[str, object] = {"model": model, "documents": {}}
    documents: dict[str, object] = {}
    for document, gold_file in CORPUS:
        source = ingest(FIXTURES / document, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
        gold = gold_candidates(source, load_gold_labels(GOLD / gold_file))
        result = extract_candidates(source, provider, model=model)
        score = score_extraction(result.candidates(), gold)
        documents[document] = {
            "score": score.model_dump(mode="json"),
            "rejected": [r.model_dump(mode="json") for r in result.rejected],
            "usage": result.usage.model_dump(),
            "predicted": [{"kind": c.kind.value, "text": c.text} for c in result.candidates()],
        }
        print(f"\n== {document}: overall {score.overall}")
        for kind in CandidateKind:
            print(f"   {kind.value:<11} {score.per_kind[kind]}")
        rejected = [(r.kind.value, r.reason.value, r.quote[:50]) for r in result.rejected]
        print(f"   rejected: {rejected}")
    results["documents"] = documents
    (RECORDINGS / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
