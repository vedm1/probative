"""Types shared by every `Provider` implementation.

These are the only shapes an agent (or anything outside `probative.llm`) is
allowed to depend on. Nothing here names a specific provider or SDK.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    """One turn in a conversation sent to a provider."""

    role: Role
    content: str


class TokenUsage(BaseModel):
    """Token accounting for a single completion.

    Every agent call is audited against this — see `CostRecord` in the
    agent contract (S1), landing at PB12.
    """

    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


OutputT = TypeVar("OutputT", bound=BaseModel)


class StructuredResult(BaseModel, Generic[OutputT]):
    """A provider completion parsed against a caller-supplied Pydantic model.

    This is the only way an agent may get typed output back from a model —
    there is no path that returns an unparsed string. See I4: what comes
    back here is *input* to a formula, never a formula's output.
    """

    output: OutputT
    usage: TokenUsage
    raw_model: str
