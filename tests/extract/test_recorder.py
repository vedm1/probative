"""The recorder/replay pair, proven without any model: a recorded response
replays through the real `LiteLLMProvider` parse path, and a changed prompt
fails loudly rather than replaying a stale answer."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from probative.extract.prompts import GeneralOutput, RawQuote
from probative.llm import LiteLLMProvider, Message
from tests.extract._recording import MissingRecordingError, Recorder, recording_key, replay

OUTPUT = GeneralOutput(needs=[RawQuote(quote="Users need a dashboard.")])


def _fake_real(**kwargs: Any) -> Any:
    return SimpleNamespace(
        model="vendor/some-model",
        choices=[SimpleNamespace(message=SimpleNamespace(content=OUTPUT.model_dump_json()))],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=15),
    )


def _call(provider: LiteLLMProvider, content: str = "doc A") -> Any:
    return provider.complete_structured(
        [Message(role="system", content="rules"), Message(role="user", content=content)],
        output_model=GeneralOutput,
        model="ignored",
    )


def test_record_then_replay_roundtrips_through_the_real_provider(tmp_path: Path) -> None:
    recorded = _call(LiteLLMProvider(completion_fn=Recorder(_fake_real, tmp_path)))
    replayed = _call(LiteLLMProvider(completion_fn=replay(tmp_path)))
    assert replayed.output == recorded.output == OUTPUT
    assert replayed.usage == recorded.usage
    assert replayed.usage.input_tokens == 120
    assert replayed.raw_model == "vendor/some-model"


def test_recording_has_only_the_fields_the_provider_reads(tmp_path: Path) -> None:
    _call(LiteLLMProvider(completion_fn=Recorder(_fake_real, tmp_path)))
    (path,) = tmp_path.glob("*.json")
    payload = json.loads(path.read_text())
    assert set(payload) == {"model", "choices", "usage"}
    assert set(payload["usage"]) == {"prompt_tokens", "completion_tokens"}
    # The prompt itself (the document) is not stored — only its hash names the file.
    assert "doc A" not in path.read_text()


def test_changed_prompt_fails_loudly_with_its_hash(tmp_path: Path) -> None:
    _call(LiteLLMProvider(completion_fn=Recorder(_fake_real, tmp_path)), "doc A")
    changed = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "doc B"},
    ]
    with pytest.raises(MissingRecordingError, match=recording_key(changed)):
        _call(LiteLLMProvider(completion_fn=replay(tmp_path)), "doc B")


def test_key_depends_on_message_content_and_order() -> None:
    a = [{"role": "user", "content": "x"}, {"role": "user", "content": "y"}]
    b = [{"role": "user", "content": "y"}, {"role": "user", "content": "x"}]
    assert recording_key(a) != recording_key(b)
    assert recording_key(a) == recording_key(list(a))


def test_recorder_returns_the_real_response_untouched(tmp_path: Path) -> None:
    response = Recorder(_fake_real, tmp_path)(messages=[{"role": "user", "content": "x"}])
    assert response.usage.prompt_tokens == 120
