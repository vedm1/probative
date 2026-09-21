"""The narrow interface every LLM backend implements.

This is the boundary the PB0 risk mitigation exists to protect: no code
outside `probative.llm` may import a provider SDK directly. Everything an
agent needs from a model comes through `Provider.complete_structured` —
structured output against a Pydantic model, plus token accounting. Which
vendor SDK sits behind it is an implementation detail of this package.
See `test_no_llm_import_leak.py`.
"""

from __future__ import annotations

from typing import Protocol

from probative.llm.types import Message, OutputT, StructuredResult


class Provider(Protocol):
    """A backend that can turn messages into a typed, structured result."""

    def complete_structured(
        self,
        messages: list[Message],
        *,
        output_model: type[OutputT],
        model: str,
    ) -> StructuredResult[OutputT]:
        """Complete `messages` and parse the response against `output_model`.

        Implementations must not return unparsed text — a caller that wants
        a typed result must get one or an exception, never a string it has
        to parse itself.
        """
        ...
