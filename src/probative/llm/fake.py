"""A `Provider` for tests: no network, no credentials, deterministic output.

Agent tests (from PB14 onward) construct a `FakeProvider` with a queue of
pre-built outputs instead of talking to a real model. This is what keeps the
default test suite runnable with zero LLM credentials in the environment (S3).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from probative.llm.types import Message, OutputT, StructuredResult, TokenUsage


class FakeProvider:
    """Returns pre-scripted `StructuredResult`s in order, one per call.

    Construct with the parsed output models the test wants back; usage is
    a fixed nominal value unless overridden.
    """

    def __init__(
        self,
        outputs: Iterable[OutputT],
        *,
        usage: TokenUsage | None = None,
    ) -> None:
        self._outputs: deque[OutputT] = deque(outputs)
        self._usage = usage or TokenUsage(input_tokens=0, output_tokens=0)

    def complete_structured(
        self,
        messages: list[Message],
        *,
        output_model: type[OutputT],
        model: str,
    ) -> StructuredResult[OutputT]:
        if not self._outputs:
            raise AssertionError("FakeProvider has no more scripted outputs")
        output = self._outputs.popleft()
        if not isinstance(output, output_model):
            raise AssertionError(
                f"FakeProvider's next output is a {type(output).__name__}, "
                f"but the caller asked for {output_model.__name__}"
            )
        return StructuredResult(output=output, usage=self._usage, raw_model=model)
