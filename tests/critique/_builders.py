"""Small builders shared by the PB9 tests. Synthetic data only."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from probative.core.critic import Finding, Severity
from probative.core.evidence import (
    EvidenceKind,
    EvidenceSpan,
    Locator,
    LocatorRegion,
    Source,
    SourceFormat,
    Tier,
)


def make_source(
    text: str, *, name: str = "doc.md", fmt: SourceFormat = SourceFormat.MARKDOWN
) -> Source:
    lines = text.splitlines(keepends=True)
    regions: list[LocatorRegion] = []
    pos = 0
    for number, line in enumerate(lines, start=1):
        regions.append(LocatorRegion(start=pos, end=pos + len(line), locator=Locator(line=number)))
        pos += len(line)
    return Source(
        id="src_0123456789abcdef",
        path=Path(name),
        sha256="0" * 64,
        format=fmt,
        tier=Tier.T4,
        kind=EvidenceKind.DOCUMENTARY,
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        extractor="test",
        extractor_version="test/1",
        text=text,
        locator_regions=regions,
    )


def span_of(source: Source, phrase: str) -> EvidenceSpan:
    start = source.text.index(phrase)
    end = start + len(phrase)
    line = source.text.count("\n", 0, start) + 1
    return EvidenceSpan(
        source_id=source.id, start=start, end=end, text=phrase, locator=Locator(line=line)
    )


def make_finding(
    *,
    critic_id: str = "space_warden",
    check_id: str = "names_feature",
    severity: Severity = Severity.BLOCK,
    target_id: str | None = "cand_need_000000000001",
    evidence: EvidenceSpan | None = None,
    message: str = "A need that names a feature.",
    remedy: str = "Say what the user gets.",
) -> Finding:
    return Finding(
        critic_id=critic_id,
        check_id=check_id,
        severity=severity,
        invariant="I3",
        message=message,
        remedy=remedy,
        target_id=target_id,
        evidence=evidence,
    )


def make_report(source: Source, findings: list[Finding], *, checked: int = 4):  # type: ignore[no-untyped-def]
    """A one-dimension, one-document report assembled the way the pipeline does."""
    from probative.core.critic import Rubric, RubricCheck
    from probative.critique.report import (
        CritiqueReport,
        DocumentSummary,
        RunStats,
        report_finding,
    )
    from probative.critique.scoring import assess_dimension, severity_counts

    rubric = Rubric(
        id="space_warden",
        severity=Severity.BLOCK,
        invariant="I3",
        checks=[RubricCheck(id="names_feature", description="d", remedy="r")],
        clean_fixtures="x",
        defect_fixtures="y",
    )
    rendered = [report_finding(f, source) for f in findings]
    dim = assess_dimension(
        rubric, "Problem framing", checked=checked, findings=findings, rendered=rendered, unjudged=0
    )
    counts = severity_counts(findings)
    doc = DocumentSummary(
        source_id=source.id,
        file_name=source.path.name,
        format=source.format,
        format_choice="detected",
        sha256=source.sha256,
        chars=len(source.text),
        pages=None,
        tier=source.tier.value,
        kind=source.kind.value,
        candidates={"need": checked},
        rejected={},
        counts=counts,
    )
    return CritiqueReport(
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        tool_version="test",
        model="test/model",
        is_reference_model=False,
        subject=source.path.name,
        documents=[doc],
        dimensions=[dim],
        totals=counts,
        skipped=[],
        run=RunStats(calls=1, input_tokens=1, output_tokens=1, wall_seconds=0.5, jobs=1),
    )
