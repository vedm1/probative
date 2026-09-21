"""Evidence-model types (docs/DESIGN.md §5.1): tier, kind, Source and
EvidenceSpan.

These are the shapes PB10's graph is built on top of, not the graph itself —
PB1 has no persistence layer. `Source.id`/`sha256` are pure functions of a
file's bytes, which is what makes ingestion idempotent (see `probative.ingest`).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class Tier(StrEnum):
    """How direct a piece of evidence is (docs/DESIGN.md §5.1)."""

    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"


class EvidenceKind(StrEnum):
    """What sort of thing a piece of evidence is (docs/DESIGN.md §5.1)."""

    CUSTOMER = "customer"
    OPERATIONAL = "operational"
    DOCUMENTARY = "documentary"
    SYSTEM = "system"
    DELIVERY = "delivery"
    MARKET = "market"


class SourceFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    CSV = "csv"
    MARKDOWN = "markdown"
    TEXT = "text"


class Locator(BaseModel):
    """A human-meaningful place within a Source.

    Every field is optional; a given format populates only the ones that
    apply to it (page/line for PDF, sheet/cell for XLSX, heading_path for
    Markdown and DOCX).
    """

    page: int | None = None
    line: int | None = None
    sheet: str | None = None
    cell: str | None = None
    heading_path: list[str] | None = None


class LocatorRegion(BaseModel):
    """One contiguous, non-overlapping slice of `Source.text`.

    A Source's regions are sorted by `start` and cover `[0, len(text))`
    with no gaps — `probative.ingest.spans` depends on this invariant.
    """

    start: int
    end: int
    locator: Locator


class Source(BaseModel):
    """A raw ingested artifact: its bytes, declared tier and kind, and the
    normalised text projection every EvidenceSpan's offsets point into."""

    id: str
    path: Path
    sha256: str
    format: SourceFormat
    tier: Tier
    kind: EvidenceKind
    ingested_at: datetime
    extractor: str
    extractor_version: str
    text: str
    locator_regions: list[LocatorRegion]


class EvidenceSpan(BaseModel):
    """A located extract — the atom of provenance (I1).

    Deliberately carries no `source_path`/`format`/`extractor_version`:
    those belong to `Source` alone (single source of record per field).
    """

    source_id: str
    start: int
    end: int
    text: str
    locator: Locator


class IngestError(Exception):
    """Base for all ingestion failures. Always names the offending file."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


class UnsupportedFormatError(IngestError):
    """The file's extension is not one PB1 recognises."""


class EmptySourceError(IngestError):
    """The file is zero bytes, or (XLSX) every sheet is empty."""


class EncryptedSourceError(IngestError):
    """The file is password-protected and no password was supplied."""


class CorruptSourceError(IngestError):
    """The file cannot be parsed as its declared format."""


class NoTextLayerError(IngestError):
    """A PDF has at least one page with no extractable text (OCR refusal)."""


class MalformedCSVError(IngestError):
    """A CSV row's column count does not match the header's."""


class SpanOutOfRangeError(IngestError):
    """`spans()` was given a range outside the source's text, or start >= end."""


class StaleNormalizationError(IngestError):
    """`reextract()` found that re-ingesting now would use a different
    normalisation version than the one the span's offsets were recorded
    against — those offsets are not guaranteed valid any more."""
