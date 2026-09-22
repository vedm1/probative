"""Structured tracker exports (PB2): Jira CSV/HTML/XML and Azure DevOps CSV
become a `Source` plus recognised `Issue` records — key, type, status,
hierarchy (`parent_key`) and, where the export has one, acceptance
criteria.

Public API: `ingest_tracker`, `issues`, `reextract_tracker`, `Issue`.
Deliberately separate from `probative.ingest`'s `ingest`/`spans`/
`reextract` (PB1): a tracker export's format cannot be sniffed from a
`.csv`/`.html`/`.xml` extension the way PB1's document formats can — the
run already knows which tracker system it's pointed at (Jira vs ADO vs
...), so the caller states `format` explicitly instead of it being
guessed.

`issues()` is a derived view, not a second source of record: it reads
`Source.locator_regions` (written by the per-format extractor) and builds
`EvidenceSpan`s through the existing `probative.ingest.spans`, so every
tracker `EvidenceSpan`'s provenance and re-extraction guarantees are
identical to PB1's.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from probative.core.evidence import (
    CorruptSourceError,
    EmptySourceError,
    EvidenceKind,
    EvidenceSpan,
    Source,
    SourceFormat,
    StaleNormalizationError,
    Tier,
)
from probative.ingest import ado_csv, jira_csv, jira_html, jira_xml, spans
from probative.ingest._extracted import ExtractedDocument
from probative.ingest._tracker_text import (
    ACCEPTANCE_CRITERIA_FIELD,
    DESCRIPTION_FIELD,
    HEADER_FIELD,
    SUMMARY_FIELD,
)

_EXTRACTORS = {
    SourceFormat.JIRA_CSV: jira_csv.extract,
    SourceFormat.JIRA_HTML: jira_html.extract,
    SourceFormat.JIRA_XML: jira_xml.extract,
    SourceFormat.ADO_CSV: ado_csv.extract,
}


class Issue(BaseModel):
    """One recognised issue/work item from a tracker export."""

    key: str
    type: str
    status: str
    parent_key: str | None
    summary: EvidenceSpan
    description: EvidenceSpan | None
    acceptance_criteria: EvidenceSpan | None


def _extract(path: Path, fmt: SourceFormat) -> ExtractedDocument:
    if fmt not in _EXTRACTORS:
        raise ValueError(f"{fmt!r} is not a tracker format PB2 recognises")
    return _EXTRACTORS[fmt](path)


def ingest_tracker(path: Path, *, format: SourceFormat, tier: Tier, kind: EvidenceKind) -> Source:
    """Ingest one tracker export, producing a `Source` whose `id`/`sha256`
    are pure functions of its bytes (idempotent, same as `ingest()`)."""
    raw = path.read_bytes()
    if len(raw) == 0:
        raise EmptySourceError(path, "file is empty")
    sha256 = hashlib.sha256(raw).hexdigest()
    doc = _extract(path, format)
    return Source(
        id=f"src_{sha256[:16]}",
        path=path,
        sha256=sha256,
        format=format,
        tier=tier,
        kind=kind,
        ingested_at=datetime.now(UTC),
        extractor=f"probative.ingest.tracker.{format.value}",
        extractor_version=doc.normalization_version,
        text=doc.text,
        locator_regions=doc.locator_regions,
    )


def issues(source: Source) -> list[Issue]:
    """Rebuild the `Issue` records a tracker `Source` was built from."""
    groups: dict[str, dict[str, tuple[int, int]]] = {}
    order: list[str] = []
    for region in source.locator_regions:
        key = region.locator.issue_key
        field = region.locator.field
        if key is None or field is None:
            continue
        if key not in groups:
            groups[key] = {}
            order.append(key)
        groups[key][field] = (region.start, region.end)

    result: list[Issue] = []
    for key in order:
        fields = groups[key]
        h_start, h_end = fields[HEADER_FIELD]
        header_text = source.text[h_start:h_end].rstrip("\n")
        _key, type_, status, parent_key_raw = header_text.split("\t")
        parent_key = parent_key_raw or None

        summary_span = spans(source, [fields[SUMMARY_FIELD]])[0]
        description_span = (
            spans(source, [fields[DESCRIPTION_FIELD]])[0] if DESCRIPTION_FIELD in fields else None
        )
        acceptance_span = (
            spans(source, [fields[ACCEPTANCE_CRITERIA_FIELD]])[0]
            if ACCEPTANCE_CRITERIA_FIELD in fields
            else None
        )

        result.append(
            Issue(
                key=key,
                type=type_,
                status=status,
                parent_key=parent_key,
                summary=summary_span,
                description=description_span,
                acceptance_criteria=acceptance_span,
            )
        )
    return result


def reextract_tracker(source: Source, span: EvidenceSpan) -> str:
    """Re-run tracker extraction on `source.path` and slice at the span's
    offsets — the tracker-format counterpart to `probative.ingest.reextract`."""
    if span.source_id != source.id:
        raise ValueError(f"span belongs to source {span.source_id!r}, not {source.id!r}")
    fresh = ingest_tracker(source.path, format=source.format, tier=source.tier, kind=source.kind)
    if fresh.extractor_version != source.extractor_version:
        raise StaleNormalizationError(
            source.path,
            f"normalisation changed ({source.extractor_version} -> "
            f"{fresh.extractor_version}); offsets recorded against the old "
            f"version are not guaranteed valid",
        )
    if fresh.sha256 != source.sha256:
        raise CorruptSourceError(source.path, "file contents changed since ingestion")
    return fresh.text[span.start : span.end]
