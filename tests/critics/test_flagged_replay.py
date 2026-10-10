"""Replays committed flagged-reply recordings (tests/fixtures/critics/recordings_flagged/)
through the real parse path, pins what they scored, and enforces the acceptance rule
fixed in `_flagged.py` before recording. Skipped per critic and split until recorded.
"""

from __future__ import annotations

from typing import Any

import pytest

import probative.critique.pipeline as pipeline_module
from probative.config import REFERENCE_MODEL
from probative.llm import LiteLLMProvider
from tests._recording import MissingRecordingError, recording_key, replay
from tests.critics._flagged import (
    CRITICS,
    FULL_RECORDINGS,
    HINT,
    SPLITS_ALL,
    acceptable,
    flagged_dir,
    load_results,
    new_flagged_critic,
)
from tests.critics._measure import measure, measure_mixed, measure_stress
from tests.critics._replay import replay_all_splits  # noqa: F401  (documented sibling)

NAMES = list(CRITICS)


def _provider(name: str) -> LiteLLMProvider:
    fns = [replay(flagged_dir(name, s), HINT) for s in SPLITS_ALL]

    def completion(**kwargs: Any) -> Any:
        for fn in fns:
            try:
                return fn(**kwargs)
            except MissingRecordingError:
                continue
        raise MissingRecordingError(recording_key(kwargs["messages"]), HINT)

    return LiteLLMProvider(completion_fn=completion)


@pytest.mark.parametrize("split", ("dev", "held_out"))
@pytest.mark.parametrize("name", NAMES)
def test_replayed_measurement_equals_the_recorded_one(name: str, split: str) -> None:
    recorded = load_results(flagged_dir(name, split))
    if recorded is None:
        pytest.skip(HINT)
    assert recorded["model"] == REFERENCE_MODEL
    corpus, _ = CRITICS[name]
    again = {
        "model": REFERENCE_MODEL,
        **measure(corpus, split, new_flagged_critic(name, _provider(name)), detail=True),
    }
    assert again == recorded


@pytest.mark.parametrize("name", NAMES)
def test_replayed_stress_and_mixed_equal_the_recorded_ones(name: str) -> None:
    recorded = load_results(flagged_dir(name, "stress"))
    if recorded is None:
        pytest.skip(HINT)
    corpus, _ = CRITICS[name]
    stress = measure_stress(corpus, new_flagged_critic(name, _provider(name)))
    mixed = measure_mixed(corpus, new_flagged_critic(name, _provider(name)))
    assert stress == recorded["stress"] and mixed == recorded["mixed"]


@pytest.mark.parametrize("name", NAMES)
def test_flagged_replies_meet_the_preregistered_rule_on_held_out(name: str) -> None:
    flagged = load_results(flagged_dir(name, "held_out"))
    full = load_results(FULL_RECORDINGS / name / "held_out")
    if flagged is None or full is None:
        pytest.skip(HINT)
    ok, detail = acceptable(full, flagged)
    assert ok, f"{name}: flagged replies fail the pre-registered rule: {detail}"


def test_the_default_reply_follows_the_calibration() -> None:
    """`critique` keeps `full` replies until every critic's held-out flagged recording
    exists and passes the pre-registered rule; this fails (it does not skip) if the
    default says `flagged` without that evidence."""
    verdicts = []
    for name in NAMES:
        flagged = load_results(flagged_dir(name, "held_out"))
        full = load_results(FULL_RECORDINGS / name / "held_out")
        verdicts.append(None if flagged is None or full is None else acceptable(full, flagged)[0])
    default = pipeline_module.CritiqueOptions(model="m").reply
    expected = "flagged" if all(v is True for v in verdicts) else "full"
    assert default == expected, f"held-out verdicts {verdicts} require the default {expected!r}"
