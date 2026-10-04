"""`extract_candidates`: one `Source` in, typed located candidates out.

Not an S1 `Agent` — `GraphState`/`RunContext` do not exist until PB12 — and it
builds no graph. It proposes nothing to the Committer; it returns candidates.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from probative.core.candidates import (
    CandidateKind,
    ClaimCandidate,
    ConstraintCandidate,
    DependencyCandidate,
    ExtractionFailedError,
    ExtractionResult,
    NeedCandidate,
    RejectedQuote,
    RejectReason,
    SegmentCandidate,
    StoryCandidate,
    candidate_id,
)
from probative.core.evidence import EvidenceSpan, Source
from probative.extract.chunking import chunk_windows
from probative.extract.prompts import PASSES, ExtractionPass, RawQuote
from probative.extract.resolve import resolve_quote
from probative.llm import Message, Provider, TokenUsage
from probative.llm.structured import complete_with_repair


def _neutralise(chunk: str) -> str:
    """Stop the document closing its own data region. Only a quote that itself
    contains the literal delimiter is affected, and it is rejected, not mangled."""
    return chunk.replace("</document>", "</ document>")


def _messages(extraction_pass: ExtractionPass, chunk: str) -> list[Message]:
    return [
        Message(role="system", content=extraction_pass.system_prompt),
        Message(role="user", content=f"<document>\n{_neutralise(chunk)}\n</document>"),
    ]


def _call(
    provider: Provider,
    extraction_pass: ExtractionPass,
    messages: list[Message],
    *,
    model: str,
    source_id: str,
) -> tuple[BaseModel, TokenUsage]:
    """One structured call, with a single repair retry on malformed output.

    A malformed reply carries no token usage, so on the repair path
    `ExtractionResult.usage` is a lower bound.
    """
    try:
        result = complete_with_repair(
            provider, messages, output_model=extraction_pass.output_model, model=model
        )
    except ValidationError as error:
        raise ExtractionFailedError(source_id, extraction_pass.name) from error
    return result.output, result.usage


def extract_candidates(
    source: Source,
    provider: Provider,
    *,
    model: str,
    max_chars_per_call: int = 60_000,
    max_quote_chars: int = 500,
    passes: Sequence[ExtractionPass] | None = None,
) -> ExtractionResult:
    """`passes=None` runs PB4's two passes. Pass `[*PASSES, SEGMENT_PASS]` to
    also extract segments (PB6-p2); the default is unchanged so PB4's recorded
    prompts keep replaying."""
    chosen = list(PASSES if passes is None else passes)
    if not chosen:
        raise ValueError("passes must name at least one extraction pass")
    if max_chars_per_call < 1:
        raise ValueError(f"max_chars_per_call must be at least 1, got {max_chars_per_call}")
    found: dict[CandidateKind, list[EvidenceSpan]] = {kind: [] for kind in CandidateKind}
    claimed: dict[CandidateKind, set[tuple[int, int]]] = {kind: set() for kind in CandidateKind}
    rejected: list[RejectedQuote] = []
    input_tokens = output_tokens = 0

    for window in chunk_windows(source, max_chars=max_chars_per_call):
        chunk = source.text[window[0] : window[1]]
        for extraction_pass in chosen:
            output, usage = _call(
                provider,
                extraction_pass,
                _messages(extraction_pass, chunk),
                model=model,
                source_id=source.id,
            )
            input_tokens += usage.input_tokens
            output_tokens += usage.output_tokens
            for field_name, kind in extraction_pass.fields.items():
                quotes: list[RawQuote] = getattr(output, field_name)
                for raw in quotes:
                    resolved = resolve_quote(
                        source,
                        raw.quote,
                        window=window,
                        claimed=claimed[kind],
                        max_quote_chars=max_quote_chars,
                    )
                    if isinstance(resolved, RejectReason):
                        rejected.append(RejectedQuote(kind=kind, quote=raw.quote, reason=resolved))
                    else:
                        claimed[kind].add((resolved.start, resolved.end))
                        found[kind].append(resolved)

    def ordered(kind: CandidateKind) -> list[EvidenceSpan]:
        return sorted(found[kind], key=lambda span: (span.start, span.end))

    return ExtractionResult(
        source_id=source.id,
        claims=[
            ClaimCandidate(id=candidate_id(CandidateKind.CLAIM, s), evidence=s)
            for s in ordered(CandidateKind.CLAIM)
        ],
        needs=[
            NeedCandidate(id=candidate_id(CandidateKind.NEED, s), evidence=s)
            for s in ordered(CandidateKind.NEED)
        ],
        stories=[
            StoryCandidate(id=candidate_id(CandidateKind.STORY, s), evidence=s)
            for s in ordered(CandidateKind.STORY)
        ],
        constraints=[
            ConstraintCandidate(id=candidate_id(CandidateKind.CONSTRAINT, s), evidence=s)
            for s in ordered(CandidateKind.CONSTRAINT)
        ],
        dependencies=[
            DependencyCandidate(id=candidate_id(CandidateKind.DEPENDENCY, s), evidence=s)
            for s in ordered(CandidateKind.DEPENDENCY)
        ],
        segments=[
            SegmentCandidate(id=candidate_id(CandidateKind.SEGMENT, s), evidence=s)
            for s in ordered(CandidateKind.SEGMENT)
        ],
        rejected=rejected,
        usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )
