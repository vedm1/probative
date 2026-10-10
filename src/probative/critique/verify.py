"""Integrity checks run before anything is written (I1, I4).

`verify_report` is the render-time cross-check CLAUDE.md names for evidence
text: each quote is compared with the source's own bytes, and each source is
re-extracted once through its format's official re-extraction API. A mismatch
fails the run; no report file is produced from a report that does not verify.

`verify_numbers` is a small `FormulaValidator`: it recomputes every number in
the report from the findings and the candidate counts and diffs it.
"""

from __future__ import annotations

from collections.abc import Mapping

from probative.core.critic import Finding, Rubric, RubricCheck, Severity
from probative.core.evidence import CorruptSourceError, Source, StaleNormalizationError
from probative.critics.scoring import score_dimension
from probative.critique.report import (
    CritiqueReport,
    DimensionResult,
    DimensionStatus,
    ReportFinding,
    ReportIntegrityError,
    locator_label,
)
from probative.critique.roster import ROSTER
from probative.critique.scoring import clean_rate, flagged_candidates, severity_counts
from probative.critique.sources import reextract_whole


def _floor(dim: DimensionResult) -> float:
    rubric = Rubric(
        id=dim.critic_id,
        severity=Severity.WARN,
        checks=[RubricCheck(id="x", description="x", remedy="x")],
        clean_fixtures="x",
        defect_fixtures="x",
    )
    stubs = [
        Finding(
            critic_id=dim.critic_id,
            check_id=f.check_id,
            severity=f.severity,
            invariant=f.invariant,
            message=f.message,
            remedy=f.remedy,
        )
        for f in dim.findings
    ]
    return score_dimension(rubric, stubs).score


def _same(a: float | None, b: float | None) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)


def _verify_dimension(dim: DimensionResult) -> None:
    where = f"dimension {dim.critic_id}"
    counts = severity_counts(dim.findings)
    if counts != dim.counts:
        raise ReportIntegrityError(f"{where}: severity counts {dim.counts} != findings {counts}")
    if flagged_candidates(dim.findings) != dim.flagged:
        raise ReportIntegrityError(f"{where}: flagged {dim.flagged} != recomputed")
    if dim.blocked != (counts.block > 0):
        raise ReportIntegrityError(f"{where}: blocked flag disagrees with findings")
    if dim.flagged > dim.checked:
        raise ReportIntegrityError(f"{where}: flagged {dim.flagged} > checked {dim.checked}")
    if dim.unjudged > 0 or dim.unextracted > 0:
        expected = DimensionStatus.INCOMPLETE
    elif dim.checked == 0:
        expected = DimensionStatus.NOT_APPLICABLE
    else:
        expected = DimensionStatus.ASSESSED
    if dim.status is not expected:
        raise ReportIntegrityError(f"{where}: status {dim.status} disagrees with its counts")
    assessed = dim.status is DimensionStatus.ASSESSED
    want_rate = clean_rate(dim.checked, dim.flagged) if assessed else None
    want_floor = _floor(dim) if assessed else None
    if not _same(dim.clean_rate, want_rate):
        raise ReportIntegrityError(f"{where}: clean_rate {dim.clean_rate} != {want_rate}")
    if not _same(dim.floor_score, want_floor):
        raise ReportIntegrityError(f"{where}: floor_score {dim.floor_score} != {want_floor}")


def verify_numbers(report: CritiqueReport) -> None:
    subjects = {e.rubric_id: e.subjects for e in ROSTER}
    for dim in report.dimensions:
        if dim.critic_id in subjects:
            counted = sum(
                doc.candidates.get(kind.value, 0)
                for doc in report.documents
                for kind in subjects[dim.critic_id]
            )
            if counted != dim.checked:
                raise ReportIntegrityError(
                    f"dimension {dim.critic_id}: checked {dim.checked} != {counted} "
                    "candidates extracted from the documents"
                )
        _verify_dimension(dim)
    every: list[ReportFinding] = [f for d in report.dimensions for f in d.findings]
    if severity_counts(every) != report.totals:
        raise ReportIntegrityError(f"totals {report.totals} != findings {severity_counts(every)}")
    for doc in report.documents:
        mine = [f for f in every if f.source_id == doc.source_id]
        if severity_counts(mine) != doc.counts:
            raise ReportIntegrityError(f"document {doc.file_name}: counts disagree with findings")
    known = {d.source_id for d in report.documents}
    if any(f.source_id not in known for f in every):
        raise ReportIntegrityError("a finding names a source that is not in the report")


def verify_report(report: CritiqueReport, sources: Mapping[str, Source]) -> None:
    verify_numbers(report)
    for dim in report.dimensions:
        for f in dim.findings:
            source = sources.get(f.source_id)
            if source is None:
                raise ReportIntegrityError(f"{dim.critic_id}: no source {f.source_id!r} to check")
            text = source.text
            if not (0 <= f.start < f.end <= len(text)) or text[f.start : f.end] != f.quote:
                raise ReportIntegrityError(
                    f"{dim.critic_id}: quote {f.quote!r} is not the source's bytes at "
                    f"({f.start}, {f.end})"
                )
            if f.locator_label != locator_label(f.locator):
                raise ReportIntegrityError(f"{dim.critic_id}: locator label disagrees")
            if not text[: f.start].endswith(f.context_before) or not text[f.end :].startswith(
                f.context_after
            ):
                raise ReportIntegrityError(f"{dim.critic_id}: context is not the source's bytes")
    for source_id in {f.source_id for d in report.dimensions for f in d.findings}:
        source = sources[source_id]
        try:
            fresh = reextract_whole(source)
        except (CorruptSourceError, StaleNormalizationError) as error:
            raise ReportIntegrityError(
                f"re-extract failed for {source.path.name}: {error}"
            ) from error
        if fresh != source.text:
            raise ReportIntegrityError(f"re-extract of {source.path.name} differs from the ingest")
