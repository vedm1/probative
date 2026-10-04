"""Typed extraction candidates (PROBATIVE_PHASE_SPECS.md, PB4).

A candidate is *not* a graph node (PB10) and *not* a claim of truth: it is a
statement a document makes, located by an `EvidenceSpan`. Nothing here can
carry a number a model might have authored (I4) — the only integers
reachable from a candidate are the span's character offsets.

Tier and evidence kind are deliberately absent: they live on `Source` and are
reached through `evidence.source_id` (single source of record, CLAUDE.md).
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from probative.core.evidence import EvidenceSpan
from probative.llm.types import TokenUsage


class CandidateKind(StrEnum):
    CLAIM = "claim"
    NEED = "need"
    STORY = "story"
    CONSTRAINT = "constraint"
    DEPENDENCY = "dependency"
    SEGMENT = "segment"


def candidate_id(kind: CandidateKind, span: EvidenceSpan) -> str:
    """The id is derived from what the candidate *is*, never authored."""
    digest = hashlib.sha256(f"{span.source_id}:{span.start}:{span.end}".encode()).hexdigest()
    return f"cand_{kind.value}_{digest[:12]}"


class _CandidateBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    evidence: EvidenceSpan

    @property
    def text(self) -> str:
        return self.evidence.text

    @model_validator(mode="after")
    def _span_is_coherent(self) -> _CandidateBase:
        ev = self.evidence
        if not (0 <= ev.start < ev.end) or len(ev.text) != ev.end - ev.start:
            raise ValueError(
                f"span ({ev.start}, {ev.end}) is not coherent with text of length {len(ev.text)}"
            )
        return self

    @model_validator(mode="after")
    def _id_is_derived(self) -> _CandidateBase:
        kind = getattr(self, "kind", None)
        if isinstance(kind, CandidateKind) and self.id != candidate_id(kind, self.evidence):
            raise ValueError(f"id {self.id!r} is not the derived id for this kind and span")
        return self


class ClaimCandidate(_CandidateBase):
    kind: Literal[CandidateKind.CLAIM] = CandidateKind.CLAIM


class NeedCandidate(_CandidateBase):
    kind: Literal[CandidateKind.NEED] = CandidateKind.NEED


class StoryCandidate(_CandidateBase):
    kind: Literal[CandidateKind.STORY] = CandidateKind.STORY


class ConstraintCandidate(_CandidateBase):
    kind: Literal[CandidateKind.CONSTRAINT] = CandidateKind.CONSTRAINT


class DependencyCandidate(_CandidateBase):
    kind: Literal[CandidateKind.DEPENDENCY] = CandidateKind.DEPENDENCY


class SegmentCandidate(_CandidateBase):
    """A statement that names or defines the group of customers the document
    says the product is for, in the document's own words (PB6-p2). It makes no
    claim that the group is a real segment; `SegmentSkeptic` asks that."""

    kind: Literal[CandidateKind.SEGMENT] = CandidateKind.SEGMENT


Candidate = Annotated[
    ClaimCandidate
    | NeedCandidate
    | StoryCandidate
    | ConstraintCandidate
    | DependencyCandidate
    | SegmentCandidate,
    Field(discriminator="kind"),
]


class RejectReason(StrEnum):
    NOT_FOUND = "not_found"
    EMPTY = "empty"
    TOO_LONG = "too_long"
    DUPLICATE = "duplicate"


class RejectedQuote(BaseModel):
    """A quote the model proposed that could not become a candidate."""

    kind: CandidateKind
    quote: str
    reason: RejectReason


class ExtractionResult(BaseModel):
    source_id: str
    claims: list[ClaimCandidate] = Field(default_factory=list)
    needs: list[NeedCandidate] = Field(default_factory=list)
    stories: list[StoryCandidate] = Field(default_factory=list)
    constraints: list[ConstraintCandidate] = Field(default_factory=list)
    dependencies: list[DependencyCandidate] = Field(default_factory=list)
    segments: list[SegmentCandidate] = Field(default_factory=list)
    rejected: list[RejectedQuote] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=lambda: TokenUsage(input_tokens=0, output_tokens=0))

    def candidates(self) -> list[Candidate]:
        """Every candidate, in document order."""
        flat: list[Candidate] = [
            *self.claims,
            *self.needs,
            *self.stories,
            *self.constraints,
            *self.dependencies,
            *self.segments,
        ]
        return sorted(flat, key=lambda c: (c.evidence.start, c.evidence.end, c.kind.value))


class ExtractionFailedError(Exception):
    """A model kept returning output that does not match the requested
    schema, after the one repair retry."""

    def __init__(self, source_id: str, pass_name: str) -> None:
        self.source_id = source_id
        self.pass_name = pass_name
        super().__init__(
            f"{source_id}: pass {pass_name!r} returned malformed output after a repair retry"
        )
