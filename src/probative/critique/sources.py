"""Find, route and load the documents a critique is pointed at.

PB2 deliberately does not sniff tracker or Confluence formats: the caller states
the format. `probative critique` has no setup (I6), so this module states it on
the caller's behalf from signatures that are unambiguous (a Jira CSV has an
`Issue key` column, an ADO CSV a `Work Item Type` column, Jira HTML a
`issuetable`, a Confluence Word export an MHTML header), records that it did so
(`format_choice`), and lets `--as` override it. Once a signature matches, the
format is committed to: a malformed Jira CSV is a skipped file with a reason,
never a quiet fallback to plain CSV.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from probative.core.evidence import (
    EvidenceKind,
    EvidenceSpan,
    IngestError,
    Locator,
    Source,
    SourceFormat,
    Tier,
)
from probative.critique.report import SkippedFile
from probative.ingest import ingest, reextract
from probative.ingest.confluence import ingest_confluence, reextract_confluence
from probative.ingest.tracker import ingest_tracker, reextract_tracker

DEFAULT_MAX_FILES = 25

_TRACKER = {
    SourceFormat.JIRA_CSV,
    SourceFormat.JIRA_HTML,
    SourceFormat.JIRA_XML,
    SourceFormat.ADO_CSV,
}
_FORCIBLE = _TRACKER | {SourceFormat.CONFLUENCE_WORD}
_PLAIN = {
    ".pdf": SourceFormat.PDF,
    ".docx": SourceFormat.DOCX,
    ".xlsx": SourceFormat.XLSX,
    ".md": SourceFormat.MARKDOWN,
    ".markdown": SourceFormat.MARKDOWN,
    ".txt": SourceFormat.TEXT,
}
_HEAD_BYTES = 8192


@dataclass(frozen=True)
class LoadedSource:
    source: Source
    format_choice: str  # "detected" | "forced"


@dataclass
class LoadResult:
    loaded: list[LoadedSource] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)


def _head(path: Path) -> str:
    with path.open("rb") as handle:
        return handle.read(_HEAD_BYTES).decode("utf-8-sig", errors="replace")


def _csv_header(path: Path) -> list[str]:
    first = _head(path).splitlines()[:1]
    if not first:
        return []
    rows = list(csv.reader(io.StringIO(first[0])))
    return [cell.strip() for cell in rows[0]] if rows else []


def sniff_format(path: Path) -> SourceFormat | None:
    """The format a file will be read as, or `None` when this tool cannot read it."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        header = _csv_header(path)
        if "Issue key" in header:
            return SourceFormat.JIRA_CSV
        if "Work Item Type" in header:
            return SourceFormat.ADO_CSV
        return SourceFormat.CSV
    if suffix in {".html", ".htm"}:
        return SourceFormat.JIRA_HTML if "issuetable" in _head(path) else None
    if suffix == ".xml":
        return SourceFormat.JIRA_XML
    if suffix == ".doc":
        head = _head(path)
        mhtml = "MIME-Version" in head and "multipart/related" in head
        return SourceFormat.CONFLUENCE_WORD if mhtml else None
    return _PLAIN.get(suffix)


def load_source(
    path: Path, *, tier: Tier, kind: EvidenceKind, forced: SourceFormat | None
) -> LoadedSource:
    """Ingest one file. Raises an `IngestError` subclass when it cannot be read."""
    if forced is not None:
        if forced not in _FORCIBLE:
            raise ValueError(
                f"--as accepts {', '.join(sorted(f.value for f in _FORCIBLE))}; "
                f"{forced.value} is chosen by file extension"
            )
        return LoadedSource(_ingest(path, forced, tier, kind), "forced")
    fmt = sniff_format(path)
    if fmt is None:
        # let PB1 raise its own typed error (unsupported extension, etc.)
        return LoadedSource(ingest(path, tier=tier, kind=kind), "detected")
    return LoadedSource(_ingest(path, fmt, tier, kind), "detected")


def _ingest(path: Path, fmt: SourceFormat, tier: Tier, kind: EvidenceKind) -> Source:
    if fmt in _TRACKER:
        return ingest_tracker(path, format=fmt, tier=tier, kind=kind)
    if fmt is SourceFormat.CONFLUENCE_WORD:
        return ingest_confluence(path, format=fmt, tier=tier, kind=kind)
    return ingest(path, tier=tier, kind=kind)


def reextract_whole(source: Source) -> str:
    """Re-run the source's own extractor over the whole text, via the official
    re-extraction API for its format (CLAUDE.md: re-extract and compare)."""
    whole = EvidenceSpan(
        source_id=source.id, start=0, end=len(source.text), text=source.text, locator=Locator()
    )
    if source.format in _TRACKER:
        return reextract_tracker(source, whole)
    if source.format is SourceFormat.CONFLUENCE_WORD:
        return reextract_confluence(source, whole)
    return reextract(source, whole)


def _reason(error: Exception) -> str:
    name = type(error).__name__
    return f"{name.replace('Error', '')}: {error}" if name != "Exception" else str(error)


def _unsupported_reason(path: Path) -> str:
    return f"Unsupported format: {path.suffix or 'no extension'} is not a document this tool reads"


def discover_and_load(
    root: Path,
    *,
    tier: Tier,
    kind: EvidenceKind,
    forced: SourceFormat | None = None,
    max_files: int = DEFAULT_MAX_FILES,
) -> LoadResult:
    if not root.exists():
        raise FileNotFoundError(root)
    if forced is not None and root.is_dir():
        raise ValueError("--as applies to a single file, not a folder")
    if root.is_dir():
        files = sorted(
            (
                p
                for p in root.rglob("*")
                if p.is_file()
                and not any(part.startswith(".") for part in p.relative_to(root).parts)
            ),
            key=lambda p: p.relative_to(root).as_posix(),
        )
    else:
        files = [root]
    result = LoadResult()
    seen: dict[str, Path] = {}
    for path in files:
        try:
            loaded = load_source(path, tier=tier, kind=kind, forced=forced)
        except IngestError as error:
            reason = (
                _unsupported_reason(path)
                if type(error).__name__ == "UnsupportedFormatError"
                else _reason(error)
            )
            result.skipped.append(SkippedFile(path=str(path), reason=reason))
            continue
        digest = loaded.source.sha256
        if digest in seen:
            result.skipped.append(
                SkippedFile(path=str(path), reason=f"duplicate of {seen[digest].name} (same bytes)")
            )
            continue
        if len(result.loaded) >= max_files:
            result.skipped.append(
                SkippedFile(path=str(path), reason=f"over the --max-files cap of {max_files}")
            )
            continue
        seen[digest] = path
        result.loaded.append(loaded)
    return result
