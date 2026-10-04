"""Hand-rolled LLM response recording for PB4 (S3: recording is a developer
action, replay is the default).

The smallest thing that works, kept under `tests/` on purpose: PB5 will decide
OI3 (vcr-style cassettes vs. a JSON store) with this as evidence, and nothing
in `src/` depends on it.

A recording is one JSON file per request, named by a hash of the request's
messages, in the same shape as tests/fixtures/llm/recorded_structured_response.json
— only the fields `LiteLLMProvider` reads. Because the prompt text is part of
the key, editing a prompt makes its recording unreachable and replay fails
loudly with the new hash, instead of silently answering an old question.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests.extract._helpers import FIXTURES

RECORDINGS = FIXTURES / "recordings"


class MissingRecordingError(Exception):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"no recording for prompt hash {key}: a prompt or document changed. "
            f"Re-record with `ANTHROPIC_API_KEY=... uv run pytest -m live "
            f"tests/extract/test_live_record.py`"
        )


def recording_key(messages: list[dict[str, str]]) -> str:
    canonical = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class Recorder:
    """A `completion_fn` that forwards to a real one and saves what comes back."""

    def __init__(self, real: Callable[..., Any], directory: Path = RECORDINGS) -> None:
        self._real = real
        self._directory = directory

    def __call__(self, **kwargs: Any) -> Any:
        response = self._real(**kwargs)
        key = recording_key(kwargs["messages"])
        self._directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": response.model,
            "choices": [{"message": {"content": response.choices[0].message.content}}],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        }
        (self._directory / f"{key}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return response


def _as_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _as_namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_as_namespace(item) for item in value]
    return value


def replay(directory: Path = RECORDINGS) -> Callable[..., Any]:
    """A `completion_fn` that answers only from recordings."""

    def completion(**kwargs: Any) -> Any:
        key = recording_key(kwargs["messages"])
        path = directory / f"{key}.json"
        if not path.exists():
            raise MissingRecordingError(key)
        return _as_namespace(json.loads(path.read_text(encoding="utf-8")))

    return completion
