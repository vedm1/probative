"""`FakeProvider` and `LiteLLMProvider` against the `Provider` contract.

`LiteLLMProvider` is exercised against a recorded fixture via its injectable
`completion_fn` — no network call, no `litellm` import, no credentials. This
is the S3 pattern: an agent test replays a recorded response instead of
calling a real model.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from probative.llm import FakeProvider, LiteLLMProvider, Message, TokenUsage
from probative.llm.provider import Provider

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "llm"
    / "recorded_structured_response.json"
)


class Greeting(BaseModel):
    text: str


def _as_namespace(value: Any) -> Any:
    """Recursively turn a JSON-decoded dict/list into attribute-accessible stubs.

    Mirrors the attribute access `LiteLLMProvider` performs on a real
    `litellm.completion()` response (`response.choices[0].message.content`, …).
    """
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _as_namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_as_namespace(item) for item in value]
    return value


def test_fake_provider_returns_scripted_output_in_order() -> None:
    provider: Provider = FakeProvider([Greeting(text="first"), Greeting(text="second")])

    first = provider.complete_structured(
        [Message(role="user", content="hi")], output_model=Greeting, model="test-model"
    )
    second = provider.complete_structured(
        [Message(role="user", content="hi again")], output_model=Greeting, model="test-model"
    )

    assert first.output == Greeting(text="first")
    assert second.output == Greeting(text="second")
    assert first.raw_model == "test-model"


def test_fake_provider_raises_when_exhausted() -> None:
    provider = FakeProvider([Greeting(text="only one")])
    provider.complete_structured([], output_model=Greeting, model="test-model")

    with pytest.raises(AssertionError):
        provider.complete_structured([], output_model=Greeting, model="test-model")


def test_fake_provider_rejects_wrong_output_type() -> None:
    class Other(BaseModel):
        n: int

    provider = FakeProvider([Greeting(text="x")])

    with pytest.raises(AssertionError):
        provider.complete_structured([], output_model=Other, model="test-model")


def test_litellm_provider_parses_recorded_response() -> None:
    raw = json.loads(FIXTURE.read_text())
    raw.pop("_comment")
    stub_response = _as_namespace(raw)

    captured_kwargs: dict[str, Any] = {}

    def fake_completion(**kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        return stub_response

    provider: Provider = LiteLLMProvider(completion_fn=fake_completion)

    result = provider.complete_structured(
        [Message(role="user", content="say hello")],
        output_model=Greeting,
        model="anthropic/claude-opus-5",
    )

    assert result.output == Greeting(text="hello from the fixture")
    assert result.usage == TokenUsage(input_tokens=42, output_tokens=7)
    assert result.raw_model == "anthropic/claude-opus-5"

    # The provider must have asked litellm for structured output against
    # our model, not left it to prompt text.
    assert captured_kwargs["response_format"] is Greeting
    assert captured_kwargs["messages"] == [{"role": "user", "content": "say hello"}]
