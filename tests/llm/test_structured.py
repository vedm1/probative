"""`complete_with_repair`: one structured call, one repair retry on a schema
failure. Extracted from PB4's extraction pipeline so critics share it."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from probative.llm import FakeProvider, Message, StructuredResult, TokenUsage
from probative.llm.structured import REPAIR_MESSAGE, complete_with_repair


class Out(BaseModel):
    items: list[str]


class _Flaky:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls: list[list[Message]] = []
        self.inner = FakeProvider(
            [Out(items=["ok"])], usage=TokenUsage(input_tokens=3, output_tokens=2)
        )

    def complete_structured(
        self, messages: list[Message], *, output_model: type[Any], model: str
    ) -> StructuredResult[Any]:
        self.calls.append(messages)
        if self.failures > 0:
            self.failures -= 1
            output_model.model_validate_json('{"items": "nope"}')
        return self.inner.complete_structured(messages, output_model=output_model, model=model)


MESSAGES = [Message(role="system", content="s"), Message(role="user", content="u")]


def test_a_good_reply_makes_one_call() -> None:
    provider = _Flaky(0)
    result = complete_with_repair(provider, MESSAGES, output_model=Out, model="m")
    assert result.output.items == ["ok"]
    assert len(provider.calls) == 1


def test_a_malformed_reply_is_retried_once_with_the_repair_message() -> None:
    provider = _Flaky(1)
    result = complete_with_repair(provider, MESSAGES, output_model=Out, model="m")
    assert result.output.items == ["ok"]
    assert len(provider.calls) == 2
    assert provider.calls[1][:-1] == MESSAGES
    assert provider.calls[1][-1] == Message(role="user", content=REPAIR_MESSAGE)


def test_a_second_malformed_reply_raises_the_validation_error() -> None:
    provider = _Flaky(2)
    with pytest.raises(ValidationError):
        complete_with_repair(provider, MESSAGES, output_model=Out, model="m")
    assert len(provider.calls) == 2
