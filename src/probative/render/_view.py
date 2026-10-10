"""Shared, pure view helpers for the critique renderers (I5).

Everything a renderer prints comes through here or straight from the report.
Strings are fixed labels, rubric strings carried by a finding, or source bytes;
numbers are formatting of numbers already in the report, or counts of its rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from probative.core.critic import Severity
from probative.critique.report import (
    CritiqueReport,
    DimensionResult,
    DimensionStatus,
    ReportFinding,
)

SEVERITY_ORDER = (Severity.BLOCK, Severity.WARN, Severity.NOTE)
SEVERITY_LABEL = {
    Severity.BLOCK: "Blocking",
    Severity.WARN: "Warnings",
    Severity.NOTE: "Notes",
}
SEVERITY_WORD = {Severity.BLOCK: "BLOCK", Severity.WARN: "WARN", Severity.NOTE: "NOTE"}
SEVERITY_GLYPH = {Severity.BLOCK: "✗", Severity.WARN: "▲", Severity.NOTE: "•"}


@dataclass(frozen=True)
class FindingGroup:
    severity: Severity
    dimension: DimensionResult
    check_id: str
    headline: str
    findings: list[ReportFinding]

    @property
    def distinct(self) -> int:
        return len({f.target_id for f in self.findings})


def finding_groups(report: CritiqueReport) -> list[FindingGroup]:
    """Findings grouped by severity, then dimension (roster order), then check
    (order of first appearance)."""
    groups: list[FindingGroup] = []
    for severity in SEVERITY_ORDER:
        for dim in report.dimensions:
            by_check: dict[str, list[ReportFinding]] = {}
            for finding in dim.findings:
                if finding.severity is severity:
                    by_check.setdefault(finding.check_id, []).append(finding)
            for check_id, rows in by_check.items():
                groups.append(FindingGroup(severity, dim, check_id, rows[0].check_headline, rows))
    return groups


def clean_cell(dim: DimensionResult) -> str:
    if dim.status is not DimensionStatus.ASSESSED or dim.clean_rate is None:
        return "—"
    return f"{dim.clean} of {dim.checked} ({dim.clean_rate * 100:.0f}%)"


def floor_cell(dim: DimensionResult) -> str:
    return "—" if dim.floor_score is None else f"{dim.floor_score:.1f}"


def status_text(dim: DimensionResult) -> str:
    if dim.status is DimensionStatus.INCOMPLETE:
        parts = []
        if dim.unjudged:
            parts.append(f"{dim.unjudged} not judged")
        if dim.unextracted:
            parts.append(f"{dim.unextracted} extraction pass failed")
        return "INCOMPLETE: " + ", ".join(parts)
    if dim.status is DimensionStatus.NOT_APPLICABLE:
        return "nothing found to check"
    word = "BLOCKED" if dim.blocked else ("warnings" if dim.counts.warn else "clean")
    extras = []
    if dim.small_sample:
        extras.append("small sample")
    if dim.cannot_tell:
        extras.append(f"{dim.cannot_tell} undecided, counted clean")
    return " · ".join([word, *extras])


def group_total(group: FindingGroup) -> str:
    """ "(k of n)" only when n is a judged denominator: an incomplete dimension has none."""
    if group.dimension.status is not DimensionStatus.ASSESSED:
        return f"({group.distinct} flagged)"
    return f"({group.distinct} of {group.dimension.checked})"


def skipped_line(report: CritiqueReport) -> str | None:
    n = len(report.skipped)
    if not n:
        return None
    return f"{n} file{'s' if n != 1 else ''} skipped, not assessed (see Coverage)"


def run_line(report: CritiqueReport) -> str:
    docs = len(report.documents)
    pages = sum(d.pages or 0 for d in report.documents)
    model = f"{report.model} (reference model)" if report.is_reference_model else report.model
    parts = [
        model,
        f"{docs} document{'s' if docs != 1 else ''}",
        f"{sum(d.chars for d in report.documents)} characters",
    ]
    if pages:
        parts.append(f"{pages} pages")
    parts += [f"{report.run.wall_seconds:.1f}s", f"{report.run.calls} successful model calls"]
    return " · ".join(parts)


def totals_line(report: CritiqueReport) -> str:
    t = report.totals
    return f"{t.block} blocking · {t.warn} warnings · {t.note} notes"


def reply_label(report: CritiqueReport) -> str:
    """How the critics were asked to reply, a fixed label (it changes what was measured)."""
    if report.run.reply == "flagged":
        return "critics reply with flagged items only"
    return "critics reply with a verdict per check"
