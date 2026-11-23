"""Types for the `Elicitor` (PB14). Frozen, validated, no number a model could supply (I4).

An answer is a choice plus, where the template allows it, the respondent's own
words. The words are kept verbatim: they become the text of a T3 claim and the
text of its evidence span (DESIGN §5.1).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from probative.core.evidence import EvidenceKind

MAX_ANSWER_CHARS = 400


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Basis(StrEnum):
    """What the respondent says their answer rests on. It decides *claim or Question*
    (OI45): it does not weight confidence."""

    OBSERVED = "observed"
    TOLD = "told"
    DOCUMENT = "document"
    BELIEF = "belief"


class AnswerKind(StrEnum):
    CONFIRM = "confirm"
    DENY = "deny"
    AMEND = "amend"
    UNKNOWN = "unknown"
    OPEN = "open"


class Family(StrEnum):
    DISCOVER = "discover"
    RECONSTRUCT = (
        "reconstruct"  # onboarding mode (I9): what appears decided, never whether it was right
    )


TemplateKind = Literal["confirm", "open", "resolve", "challenge"]


class Option(_Frozen):
    label: str = Field(min_length=1)
    kind: AnswerKind


class QuestionTemplate(_Frozen):
    id: str = Field(min_length=1)
    family: Family
    modes: tuple[str, ...] = Field(min_length=1)
    kind: TemplateKind
    text: str = Field(min_length=1)
    options: tuple[Option, ...] = Field(min_length=2)
    evidence_kind: EvidenceKind | None = None  # None: inherit from the claim it is about


class Topic(_Frozen):
    id: str = Field(min_length=1)
    family: Family
    question: str = Field(min_length=1)
    evidence_kind: EvidenceKind


class AskedQuestion(_Frozen):
    """One filled question, as the person sees it."""

    index: int = Field(ge=0)
    template_id: str
    subject_ref: str  # a graph node id or a topic id
    text: str
    options: tuple[Option, ...]
    evidence_kind: EvidenceKind | None


class RawAnswer(_Frozen):
    """What a `Respondent` returns for one question."""

    kind: AnswerKind
    text: str = ""
    basis: Basis | None = None
    basis_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _coherent(self) -> RawAnswer:
        if len(self.text) > MAX_ANSWER_CHARS:
            raise ValueError(f"an answer is at most {MAX_ANSWER_CHARS} characters")
        if "\n" in self.text or "\r" in self.text:
            raise ValueError("an answer is one line")
        if self.kind in (AnswerKind.OPEN, AnswerKind.AMEND) and not self.text.strip():
            raise ValueError(f"a {self.kind.value} answer carries the respondent's words")
        if self.kind is AnswerKind.UNKNOWN and self.basis not in (None, Basis.BELIEF):
            raise ValueError("an unknown answer has no basis")
        if self.basis_count is not None and self.basis is not Basis.OBSERVED:
            raise ValueError("a count belongs to an observed basis")
        return self


class Turn(_Frozen):
    """One recorded question and answer. `prev_hash` chains the file: an edited
    or removed line breaks the chain and the session is refused."""

    index: int = Field(ge=0)
    round: int = Field(ge=0)
    template_id: str
    subject_ref: str
    question_text: str
    options: tuple[Option, ...]
    evidence_kind: EvidenceKind | None
    answer_kind: AnswerKind
    answer_text: str
    basis: Basis | None
    basis_count: int | None
    asked_at: datetime
    prev_hash: str


class GainReport(_Frozen):
    """What one answer changed in the graph. Counts and one difference of
    registered values; nothing here is authored (I4)."""

    new_claims: int = Field(ge=0)
    confidence_delta: float = Field(ge=0)
    questions_closed: int = Field(ge=0)
    contradictions: int = Field(ge=0)
    questions_opened: int = Field(ge=0)

    @property
    def wasted(self) -> bool:
        """An `unknown` opens a Question, but that is a recorded gap, not gain."""
        return (
            self.new_claims == 0
            and self.confidence_delta == 0
            and self.questions_closed == 0
            and self.contradictions == 0
        )


class ElicitorInput(BaseModel):
    topic: str = "general"
    max_rounds: int = Field(default=4, ge=1)
    round_size: int = Field(default=3, ge=1)
    quiet_rounds: int = Field(default=2, ge=1)


class Respondent(Protocol):
    """Whatever puts a round of questions to a person. PB14 ships a replay respondent;
    the terminal one is PB14-p2 (OI49)."""

    def answer(self, round_: tuple[AskedQuestion, ...]) -> tuple[RawAnswer, ...]: ...
