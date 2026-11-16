"""Replays the recorded judge answers (no key, no network) and pins what they scored.

Until a split has been recorded the test for it SKIPS, and says why: the judge is
unmeasured, which is a fact the phase notes must state (PB13 gating check 3). These
tests hold the prompt, rubric and fixtures to the numbers the model earned when recorded;
editing any of them breaks the recording key on purpose. Synthetic, single-author data."""

from __future__ import annotations

import json
from typing import Any

import pytest

from probative.config import REFERENCE_MODEL
from probative.llm import LiteLLMProvider
from tests._recording import replay
from tests.ledger._measure import HINT, RECORDINGS, judge_split, score

SPLITS = ("dev", "held_out")


def recorded(name: str) -> dict[str, Any]:
    path = RECORDINGS / name / "results.json"
    if not path.exists():
        pytest.skip(f"the judge is not recorded for {name}: unmeasured. {HINT}")
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return raw


@pytest.mark.parametrize("name", [*SPLITS, "stress"])
def test_replay_reproduces_the_recorded_verdicts(name: str) -> None:
    results = recorded(name)
    provider = LiteLLMProvider(completion_fn=replay(RECORDINGS / name, HINT))
    assert judge_split(provider, REFERENCE_MODEL, name) == results["verdicts"]
    assert results["model"] == REFERENCE_MODEL


# Measured 2026-11-16 on anthropic/claude-sonnet-5 with the rubric as edited on 2026-11-14:
# dev, then stress, then held_out, once each. The rubric was edited after held_out had been
# read (2026-11-13: 11/12 caught, 1 false positive, kh01), so held_out is a DEV result here, not
# an out-of-sample one (OI17). The gating target is still NOT met: ch11 is missed. Pinned so the
# numbers cannot drift unseen.
MEASURED = {
    "dev": {"caught": 12, "missed": [], "false_positives": []},
    "held_out": {"caught": 11, "missed": ["ch11"], "false_positives": []},
}


@pytest.mark.parametrize("name", SPLITS)
def test_the_judge_scored_what_was_recorded(name: str) -> None:
    scored = score(name, recorded(name)["verdicts"])
    want = MEASURED[name]
    assert (scored.caught, scored.missed, scored.false_positives) == (
        want["caught"], want["missed"], want["false_positives"]
    )  # fmt: skip


def test_stress_cases_scored_seven_of_eight_as_labelled() -> None:
    scored = score("stress", recorded("stress")["verdicts"])
    assert scored.as_labelled == 7  # only s05 (two different features) is off: cannot_tell
