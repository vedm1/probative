"""One structured call with a single repair retry.

Shared by PB4's extractor and PB5's critics: a model that returns something
that does not match the requested schema gets exactly one more try, then the
`ValidationError` propagates for the caller to wrap in its own typed error.
Provider and network errors are not caught here.
"""

from __future__ import annotations

from pydantic import ValidationError

from probative.llm.provider import Provider
from probative.llm.types import Message, OutputT, StructuredResult

REPAIR_MESSAGE = (
    "The output must be only valid JSON that matches the required schema exactly. "
    "Reply again with only that JSON."
)


def complete_with_repair(
    provider: Provider,
    messages: list[Message],
    *,
    output_model: type[OutputT],
    model: str,
) -> StructuredResult[OutputT]:
    """A malformed reply carries no token usage, so on the repair path the
    returned usage covers only the successful call (a lower bound)."""
    try:
        return provider.complete_structured(messages, output_model=output_model, model=model)
    except ValidationError:
        return provider.complete_structured(
            [*messages, Message(role="user", content=REPAIR_MESSAGE)],
            output_model=output_model,
            model=model,
        )
