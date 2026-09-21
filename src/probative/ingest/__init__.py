"""Turn a folder of ordinary documents into `Source` and `EvidenceSpan`
records whose offsets survive re-extraction (PROBATIVE_PHASE_SPECS.md, PB1).

Public API: `ingest`, `spans`, `reextract`. Everything else in this package
is per-format extraction plumbing.
"""

from __future__ import annotations

import hashlib
from bisect import bisect_right
from datetime import UTC, datetime
from pathlib import Path

from probative.core.evidence import CorruptSourceError as CorruptSourceError
from probative.core.evidence import (
    EmptySourceError,
    EvidenceKind,
    EvidenceSpan,
    Locator,
    LocatorRegion,
    Source,
    SourceFormat,
    SpanOutOfRangeError,
    StaleNormalizationError,
    Tier,
    UnsupportedFormatError,
)
from probative.ingest import csv_, docx_, markdown, pdf, text, xlsx
from probative.ingest._extracted import ExtractedDocument

__all__ = ["ingest", "reextract", "spans"]

_EXTENSION_FORMAT: dict[str, SourceFormat] = {
    ".pdf": SourceFormat.PDF,
    ".docx": SourceFormat.DOCX,
    ".xlsx": SourceFormat.XLSX,
    ".csv": SourceFormat.CSV,
    ".md": SourceFormat.MARKDOWN,
    ".markdown": SourceFormat.MARKDOWN,
    ".txt": SourceFormat.TEXT,
}

_EXTRACTORS = {
    SourceFormat.PDF: pdf.extract,
    SourceFormat.DOCX: docx_.extract,
    SourceFormat.XLSX: xlsx.extract,
    SourceFormat.CSV: csv_.extract,
    SourceFormat.MARKDOWN: markdown.extract,
    SourceFormat.TEXT: text.extract,
}


def _detect_format(path: Path) -> SourceFormat:
    fmt = _EXTENSION_FORMAT.get(path.suffix.lower())
    if fmt is None:
        raise UnsupportedFormatError(path, f"unrecognised extension {path.suffix!r}")
    return fmt


def _extract(path: Path, fmt: SourceFormat) -> ExtractedDocument:
    return _EXTRACTORS[fmt](path)


def ingest(path: Path, *, tier: Tier, kind: EvidenceKind) -> Source:
    """Ingest one file, producing a `Source` whose `id`/`sha256` are pure
    functions of its bytes — re-ingesting the same file is idempotent."""
    raw = path.read_bytes()
    if len(raw) == 0:
        raise EmptySourceError(path, "file is empty")
    sha256 = hashlib.sha256(raw).hexdigest()
    fmt = _detect_format(path)
    doc = _extract(path, fmt)
    return Source(
        id=f"src_{sha256[:16]}",
        path=path,
        sha256=sha256,
        format=fmt,
        tier=tier,
        kind=kind,
        ingested_at=datetime.now(UTC),
        extractor=f"probative.ingest.{fmt.value}",
        extractor_version=doc.normalization_version,
        text=doc.text,
        locator_regions=doc.locator_regions,
    )


def _locator_for(regions: list[LocatorRegion], offset: int) -> Locator:
    starts = [r.start for r in regions]
    idx = bisect_right(starts, offset) - 1
    if idx < 0 or not (regions[idx].start <= offset < regions[idx].end):
        raise AssertionError(f"locator_regions do not cover offset {offset} — extractor bug")
    return regions[idx].locator


def spans(source: Source, ranges: list[tuple[int, int]]) -> list[EvidenceSpan]:
    """Take spans at `ranges` (character offsets into `source.text`).

    A range that straddles two locator regions is located by its first
    character — offsets are the source of truth for provenance; the
    locator is a best-effort human aid.
    """
    result = []
    for start, end in ranges:
        if not (0 <= start < end <= len(source.text)):
            raise SpanOutOfRangeError(
                source.path,
                f"range ({start}, {end}) invalid for text of length {len(source.text)}",
            )
        locator = _locator_for(source.locator_regions, start)
        result.append(
            EvidenceSpan(
                source_id=source.id,
                start=start,
                end=end,
                text=source.text[start:end],
                locator=locator,
            )
        )
    return result


def reextract(source: Source, span: EvidenceSpan) -> str:
    """Re-run extraction on `source.path` and slice at the span's offsets.

    Raises `StaleNormalizationError` if the normalisation algorithm has
    changed since `source` was ingested (its offsets are not guaranteed
    valid any more), and `CorruptSourceError` if the file's bytes have
    changed on disk since ingestion.
    """
    if span.source_id != source.id:
        raise ValueError(f"span belongs to source {span.source_id!r}, not {source.id!r}")
    fresh = ingest(source.path, tier=source.tier, kind=source.kind)
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
