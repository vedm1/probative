"""The only module in `probative` allowed to import `litellm`.

`litellm.completion` is called with a Pydantic model as `response_format`,
which LiteLLM turns into a provider-appropriate structured-output request.
The import is deferred to call time so `import probative` (and `probative
--version`) never pays LiteLLM's import cost and never requires it to be
installed correctly on a machine that only wants the CLI shell.

`completion_fn` is injectable so tests can replay a recorded response
without importing `litellm` or making a network call — see
`tests/llm/test_provider.py` and `tests/fixtures/llm/`. This is what keeps
this provider's tests in the default (no-credentials) suite per S3.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from probative.llm.types import Message, OutputT, StructuredResult, TokenUsage

# Signature-compatible with `litellm.completion`: keyword args in, an object
# exposing `.choices[0].message.content`, `.usage.{prompt,completion}_tokens`
# and `.model` out.
CompletionFn = Callable[..., Any]


class LiteLLMProvider:
    """`Provider` backed by LiteLLM's multi-vendor `completion` call."""

    def __init__(
        self,
        *,
        completion_fn: CompletionFn | None = None,
        num_retries: int | None = None,
        timeout: float | None = None,
    ) -> None:
        # Both are forwarded to `completion` only when set, so a provider built
        # without them sends exactly the request it always did (recordings are
        # keyed on messages, and are unaffected either way). `max_tokens` and
        # `temperature` are still not set: OI19.
        if num_retries is not None and num_retries < 0:
            raise ValueError(f"num_retries must be at least 0, got {num_retries}")
        self._num_retries = num_retries
        self._timeout = timeout
        # None in production: resolved lazily to the real `litellm.completion`
        # on first use. A test passes its own fixture-backed callable.
        self._completion_fn = completion_fn

    def _completion(self) -> CompletionFn:
        if self._completion_fn is not None:
            return self._completion_fn
        # This module is exempted from the TID251 litellm ban — see pyproject.toml.
        import litellm

        return cast(CompletionFn, litellm.completion)

    def complete_structured(
        self,
        messages: list[Message],
        *,
        output_model: type[OutputT],
        model: str,
    ) -> StructuredResult[OutputT]:
        completion = self._completion()
        raw_messages = [{"role": message.role, "content": message.content} for message in messages]

        extra: dict[str, Any] = {}
        if self._num_retries is not None:
            extra["num_retries"] = self._num_retries
        if self._timeout is not None:
            extra["timeout"] = self._timeout
        response = completion(
            model=model,
            messages=raw_messages,
            response_format=output_model,
            **extra,
        )

        content = response.choices[0].message.content
        output = output_model.model_validate_json(content)
        usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
        return StructuredResult(output=output, usage=usage, raw_model=response.model)
