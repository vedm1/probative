"""`probative critique` (PROBATIVE_PHASE_SPECS.md PB9): point it at a document or
a folder, get a scored teardown whose every finding quotes the source.

Public API: `critique` (discover, load, run, verify), `CritiqueReport`,
`CritiqueOptions`. The report is verified against the sources before anyone can
render it: no file is produced from a report that does not check out.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from probative.core.evidence import EvidenceKind, Source, SourceFormat, Tier
from probative.critique.pipeline import CritiqueOptions, run_critique
from probative.critique.report import CritiqueReport, ReportIntegrityError, SkippedFile
from probative.critique.sources import DEFAULT_MAX_FILES, discover_and_load
from probative.critique.verify import verify_report
from probative.llm import Provider


class NoReadableInputError(Exception):
    """Nothing the tool can read was found at the path given."""

    def __init__(self, path: Path, skipped: list[SkippedFile]) -> None:
        self.path = path
        self.skipped = skipped
        reasons = "; ".join(f"{Path(s.path).name}: {s.reason}" for s in skipped[:5])
        super().__init__(f"no readable document at {path}" + (f" ({reasons})" if reasons else ""))


@dataclass(frozen=True)
class CritiqueRun:
    report: CritiqueReport
    sources: dict[str, Source]


def critique(
    path: Path,
    provider: Provider,
    options: CritiqueOptions,
    *,
    tier: Tier = Tier.T4,
    kind: EvidenceKind = EvidenceKind.DOCUMENTARY,
    forced: SourceFormat | None = None,
    max_files: int = DEFAULT_MAX_FILES,
) -> CritiqueRun:
    result = discover_and_load(path, tier=tier, kind=kind, forced=forced, max_files=max_files)
    if not result.loaded:
        raise NoReadableInputError(path, result.skipped)
    subject = path.resolve().name
    report = run_critique(subject, result.loaded, result.skipped, provider, options)
    sources = {item.source.id: item.source for item in result.loaded}
    verify_report(report, sources)
    return CritiqueRun(report, sources)


__all__ = [
    "CritiqueOptions",
    "CritiqueReport",
    "CritiqueRun",
    "NoReadableInputError",
    "ReportIntegrityError",
    "critique",
]
