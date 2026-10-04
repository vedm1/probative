"""Replay and record locations for the PB5 critic recordings:
tests/fixtures/critics/recordings/<critic>/<split>/*.json + results.json."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests._recording import MissingRecordingError, recording_key, replay
from tests.critics._paths import FIXTURES

RECORDINGS = FIXTURES / "recordings"
RERECORD_HINT = (
    "Re-record with `ANTHROPIC_API_KEY=... PB5_SPLIT=<dev|held_out> uv run pytest -m live "
    "tests/critics/test_pb5_live_record.py -s`. A prompt or rubric edit after held-out results "
    "exist demotes held_out to dev: write fresh held-out fixtures first."
)


def recording_dir(critic: str, split: str) -> Path:
    return RECORDINGS / critic / split


def replay_all_splits(critic: str, splits: tuple[str, ...]) -> Callable[..., Any]:
    """A `completion_fn` that answers from any of a critic's split recordings.
    The prompt hash includes the candidate text, so splits cannot collide."""
    fns = [replay(recording_dir(critic, s), RERECORD_HINT) for s in splits]

    def completion(**kwargs: Any) -> Any:
        for fn in fns:
            try:
                return fn(**kwargs)
            except MissingRecordingError:
                continue
        raise MissingRecordingError(recording_key(kwargs["messages"]), RERECORD_HINT)

    return completion
