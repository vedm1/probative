"""Hand-rolled LLM response recording (S3: recording is a developer action,
replay is the default). OI3, decided in PB5: kept, and shared by every phase
that records model output (PB4 extraction, PB5 critics).

It records at the `completion_fn` seam, so `LiteLLMProvider`'s real parse path
runs on replay, and it keys by prompt hash so a prompt edit fails loudly. A
vcr-style cassette would record HTTP instead: that couples to litellm
internals and puts request headers on a public repo. Kept under `tests/`;
nothing in `src/` depends on it.

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


class MissingRecordingError(Exception):
    def __init__(self, key: str, rerecord_hint: str = "re-record it") -> None:
        self.key = key
        super().__init__(
            f"no recording for prompt hash {key}: a prompt or document changed. {rerecord_hint}"
        )


def recording_key(messages: list[dict[str, str]]) -> str:
    canonical = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class Recorder:
    """A `completion_fn` that forwards to a real one and saves what comes back."""

    def __init__(self, real: Callable[..., Any], directory: Path) -> None:
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


def replay(directory: Path, rerecord_hint: str = "re-record it") -> Callable[..., Any]:
    """A `completion_fn` that answers only from recordings."""

    def completion(**kwargs: Any) -> Any:
        key = recording_key(kwargs["messages"])
        path = directory / f"{key}.json"
        if not path.exists():
            raise MissingRecordingError(key, rerecord_hint)
        return _as_namespace(json.loads(path.read_text(encoding="utf-8")))

    return completion
