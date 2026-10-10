"""The shape every critique renderer reads (PROBATIVE_PHASE_SPECS.md PB9).

`CritiqueReport` is a projection (I5): every string in it is a fixed label, a
rubric string carried by a `Finding`, or bytes of the source document. Every
number in it is a pure function of findings and candidate counts (I4), and
`probative.critique.verify` recomputes them. A finding that cannot name a quote
in a source is not a blank cell, it is a `ReportIntegrityError` (I1).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from probative.core.critic import Finding, Severity
from probative.core.evidence import Locator, Source, SourceFormat

SCHEMA_VERSION = "1"
CONTEXT_CHARS = 240
SMALL_SAMPLE = 5  # fewer candidates than this is labelled "small sample"


class ReportIntegrityError(Exception):
    """The report would say something the sources or the arithmetic do not support."""


class DimensionStatus(StrEnum):
    ASSESSED = "assessed"
    NOT_APPLICABLE = "not_applicable"
    INCOMPLETE = "incomplete"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class SeverityCounts(_Frozen):
    block: int = 0
    warn: int = 0
    note: int = 0


def locator_label(locator: Locator) -> str:
    """A deterministic human label for a locator, from the fields it has."""
    if locator.sheet is not None and locator.cell is not None:
        return f"{locator.sheet}!{locator.cell}"
    parts: list[str] = []
    if locator.issue_key:
        parts.append(locator.issue_key)
    if locator.field:
        parts.append(locator.field)
    if locator.page is not None:
        parts.append(f"p.{locator.page}")
    if locator.line is not None:
        parts.append(f"line {locator.line}")
    if locator.heading_path:
        parts.append(" > ".join(locator.heading_path))
    return " · ".join(parts) if parts else "location unknown"


class ReportFinding(_Frozen):
    critic_id: str
    check_id: str
    check_headline: str  # the rubric's own first sentence for the check
    severity: Severity
    invariant: str | None
    message: str
    detail: str  # what `message` says beyond its `check: “quote” — headline` prefix
    remedy: str
    target_id: str
    source_id: str
    quote: str
    start: int
    end: int
    locator: Locator
    locator_label: str
    context_before: str
    context_after: str
    context_clipped_before: bool
    context_clipped_after: bool


def _clip_before(text: str, start: int) -> tuple[str, bool]:
    lo = max(0, start - CONTEXT_CHARS)
    chunk = text[lo:start]
    if lo == 0:
        return chunk, False
    if not text[lo - 1].isspace() and not chunk[:1].isspace():
        cut = next((i for i, ch in enumerate(chunk) if ch.isspace()), None)
        chunk = "" if cut is None else chunk[cut:].lstrip(" ")
    return chunk, True


def _clip_after(text: str, end: int) -> tuple[str, bool]:
    hi = min(len(text), end + CONTEXT_CHARS)
    chunk = text[end:hi]
    if hi == len(text):
        return chunk, False
    if not text[hi].isspace() and not chunk[-1:].isspace():
        cut = next((i for i in range(len(chunk) - 1, -1, -1) if chunk[i].isspace()), None)
        chunk = "" if cut is None else chunk[:cut].rstrip(" ")
    return chunk, True


def report_finding(
    finding: Finding, source: Source, *, headline: str | None = None
) -> ReportFinding:
    """Build a report row, or raise: no evidence, no target, a span from another
    source or a quote that is not the source's own bytes is never rendered (I1)."""
    where = f"{finding.critic_id}/{finding.check_id}"
    if finding.evidence is None:
        raise ReportIntegrityError(f"{where}: finding has no evidence span")
    if finding.target_id is None:
        raise ReportIntegrityError(f"{where}: finding has no target candidate")
    ev = finding.evidence
    if ev.source_id != source.id:
        raise ReportIntegrityError(
            f"{where}: evidence belongs to source {ev.source_id!r}, not {source.id!r}"
        )
    if (
        not (0 <= ev.start < ev.end <= len(source.text))
        or source.text[ev.start : ev.end] != ev.text
    ):
        raise ReportIntegrityError(
            f"{where}: quote does not match the source bytes at ({ev.start}, {ev.end})"
        )
    before, clipped_before = _clip_before(source.text, ev.start)
    after, clipped_after = _clip_after(source.text, ev.end)
    head = headline or finding.check_id
    prefix = f"{finding.check_id}: “{ev.text}” — {head}"
    detail = (
        finding.message[len(prefix) :].strip()
        if finding.message.startswith(prefix)
        else (finding.message)
    )
    return ReportFinding(
        critic_id=finding.critic_id,
        check_id=finding.check_id,
        check_headline=head,
        detail=detail,
        severity=finding.severity,
        invariant=finding.invariant,
        message=finding.message,
        remedy=finding.remedy,
        target_id=finding.target_id,
        source_id=source.id,
        quote=ev.text,
        start=ev.start,
        end=ev.end,
        locator=ev.locator,
        locator_label=locator_label(ev.locator),
        context_before=before,
        context_after=after,
        context_clipped_before=clipped_before,
        context_clipped_after=clipped_after,
    )


class DimensionResult(_Frozen):
    critic_id: str
    label: str
    invariant: str | None
    status: DimensionStatus
    checked: int
    flagged: int
    clean_rate: float | None
    floor_score: float | None
    blocked: bool
    counts: SeverityCounts
    unjudged: int = 0
    unextracted: int = 0  # extraction passes feeding this critic that failed
    cannot_tell: int = 0  # judgements the model declined; counted as clean, so shown
    findings: list[ReportFinding]

    @property
    def clean(self) -> int:
        return self.checked - self.flagged

    @property
    def small_sample(self) -> bool:
        return self.status is DimensionStatus.ASSESSED and self.checked < SMALL_SAMPLE


class DocumentSummary(_Frozen):
    source_id: str
    file_name: str
    format: SourceFormat
    format_choice: str  # "detected" | "forced"
    sha256: str
    chars: int
    pages: int | None
    tier: str  # recorded, never rendered: a default, not a judgement
    kind: str
    candidates: dict[str, int]
    rejected: dict[str, int]
    counts: SeverityCounts


class SkippedFile(_Frozen):
    path: str
    reason: str


class RunStats(_Frozen):
    calls: int
    input_tokens: int
    output_tokens: int
    wall_seconds: float
    jobs: int
    reply: str = "full"  # how the critics were asked to reply: "full" or "flagged"


class CritiqueReport(_Frozen):
    schema_version: str = SCHEMA_VERSION
    generated_at: datetime
    tool_version: str
    model: str
    is_reference_model: bool
    subject: str  # the file or folder name the run was pointed at
    documents: list[DocumentSummary]
    dimensions: list[DimensionResult]
    totals: SeverityCounts
    skipped: list[SkippedFile]
    run: RunStats

    @property
    def incomplete(self) -> bool:
        return any(d.status is DimensionStatus.INCOMPLETE for d in self.dimensions)
