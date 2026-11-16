"""Records real model answers for the contradiction judge and scores them. Never runs
in default CI (`-m live`). A developer action:

    ANTHROPIC_API_KEY=sk-... PB13_SPLIT=dev uv run pytest -m live \\
        tests/ledger/test_live_record_contradict.py -s

Record `dev` first, then `stress`, then `held_out`, and say so in the notes: the
held-out split is for reading once, after the rubric is fixed. Re-recording a split
deletes its directory first. The fixtures are synthetic and single-author (OI4, OI21)."""

from __future__ import annotations

import json
import os
import shutil

import pytest

from probative.config import REFERENCE_MODEL
from probative.llm import LiteLLMProvider
from tests._recording import Recorder
from tests.ledger._measure import RECORDINGS, judge_split, score

pytestmark = pytest.mark.live


def test_record_and_measure_one_split() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    name = os.environ.get("PB13_SPLIT", "")
    if name not in {"dev", "held_out", "stress"}:
        pytest.skip("set PB13_SPLIT to dev, stress or held_out")
    real = LiteLLMProvider()._completion()  # this module may not import litellm (TID251)
    target = RECORDINGS / name
    shutil.rmtree(target, ignore_errors=True)
    provider = LiteLLMProvider(completion_fn=Recorder(real, target))
    scored = score(name, judge_split(provider, REFERENCE_MODEL, name))
    (target / "results.json").write_text(
        json.dumps(
            {
                "model": REFERENCE_MODEL,
                "verdicts": scored.verdicts,
                "caught": scored.caught,
                "missed": scored.missed,
                "false_positives": scored.false_positives,
                "as_labelled": scored.as_labelled,
                "total": scored.total,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{name}: caught {scored.caught}, missed {scored.missed}, false positives "
        f"{scored.false_positives}, as labelled {scored.as_labelled}/{scored.total}"
    )
