"""A real call through `LiteLLMProvider`. Never runs in default CI.

Excluded by `addopts = -m "not live"` (pyproject.toml). Run explicitly with:

    ANTHROPIC_API_KEY=sk-... uv run pytest -m live
"""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

from probative.llm import LiteLLMProvider, Message

pytestmark = pytest.mark.live


class Greeting(BaseModel):
    text: str


def test_litellm_provider_completes_against_a_real_model() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    provider = LiteLLMProvider()

    result = provider.complete_structured(
        [Message(role="user", content="Reply with the single word: hello")],
        output_model=Greeting,
        model="anthropic/claude-haiku-4-5",
    )

    assert isinstance(result.output, Greeting)
    assert result.usage.total_tokens > 0
