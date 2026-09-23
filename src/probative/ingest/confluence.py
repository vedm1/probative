"""Confluence exports (PB2-p2): a per-page "Export to Word" (MHTML behind a
`.doc` extension) becomes a plain `Source` — no derived record type, unlike
PB2's tracker `Issue`s, because a Confluence page carries no issue key,
status or hierarchy (confirmed against two real exports; see
`probative.ingest.confluence_word`).

Public API: `ingest_confluence`, `reextract_confluence`. Deliberately
separate from `probative.ingest`'s `ingest`/`reextract` (PB1), for the same
reason PB2's `tracker.py` is separate from it: a Confluence Word export's
real format can't be sniffed from its `.doc` extension — that extension
also means genuine legacy binary Word, which this codebase does not
support — so the caller states `format` explicitly instead of it being
guessed. Provenance is not reimplemented: callers use PB1's existing
`probative.ingest.spans()` directly against the resulting `Source`, since
there is no `issues()`-style derived view to build here.

The other real Confluence export variant — "Export to PDF" — needs no
module here at all: it is a well-formed PDF and is ingested through PB1's
existing `probative.ingest.ingest()` / `SourceFormat.PDF` unchanged.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

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
from probative.ingest import confluence_word
from probative.ingest._extracted import ExtractedDocument

_EXTRACTORS = {SourceFormat.CONFLUENCE_WORD: confluence_word.extract}


def _extract(path: Path, fmt: SourceFormat) -> ExtractedDocument:
    if fmt not in _EXTRACTORS:
        raise ValueError(f"{fmt!r} is not a Confluence format PB2-p2 recognises")
    return _EXTRACTORS[fmt](path)


def ingest_confluence(
    path: Path, *, format: SourceFormat, tier: Tier, kind: EvidenceKind
) -> Source:
    """Ingest one Confluence export, producing a `Source` whose `id`/`sha256`
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
        extractor=f"probative.ingest.confluence.{format.value}",
        extractor_version=doc.normalization_version,
        text=doc.text,
        locator_regions=doc.locator_regions,
    )


def reextract_confluence(source: Source, span: EvidenceSpan) -> str:
    """Re-run Confluence extraction on `source.path` and slice at the
    span's offsets — the Confluence counterpart to
    `probative.ingest.reextract`."""
    if span.source_id != source.id:
        raise ValueError(f"span belongs to source {span.source_id!r}, not {source.id!r}")
    fresh = ingest_confluence(source.path, format=source.format, tier=source.tier, kind=source.kind)
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
