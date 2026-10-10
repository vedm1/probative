from __future__ import annotations

from pathlib import Path

import pytest

from probative.core.critic import Severity
from probative.core.evidence import EvidenceKind, Tier
from probative.critique.report import ReportIntegrityError, SeverityCounts
from probative.critique.sources import load_source
from probative.critique.verify import verify_numbers, verify_report
from tests.critique._builders import make_finding, make_report, make_source, span_of

SOURCE = make_source("Users need a button. Users need a dashboard.\n")


def _report():  # type: ignore[no-untyped-def]
    findings = [
        make_finding(evidence=span_of(SOURCE, "button"), target_id="c1"),
        make_finding(evidence=span_of(SOURCE, "dashboard"), target_id="c2", severity=Severity.WARN),
    ]
    return make_report(SOURCE, findings, checked=4)


def test_numbers_verify_on_an_honest_report() -> None:
    verify_numbers(_report())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.model_copy(update={"flagged": 1}),
        lambda d: d.model_copy(update={"clean_rate": 0.9}),
        lambda d: d.model_copy(update={"floor_score": 10.0}),
        lambda d: d.model_copy(update={"blocked": False}),
        lambda d: d.model_copy(update={"counts": SeverityCounts(block=0, warn=2, note=0)}),
    ],
)
def test_a_tampered_dimension_number_fails(mutate) -> None:  # type: ignore[no-untyped-def]
    report = _report()
    bad = report.model_copy(update={"dimensions": [mutate(report.dimensions[0])]})
    with pytest.raises(ReportIntegrityError):
        verify_numbers(bad)


def test_totals_must_equal_the_findings() -> None:
    report = _report()
    bad = report.model_copy(update={"totals": SeverityCounts(block=5)})
    with pytest.raises(ReportIntegrityError, match="totals"):
        verify_numbers(bad)


def test_document_counts_must_equal_their_findings() -> None:
    report = _report()
    doc = report.documents[0].model_copy(update={"counts": SeverityCounts()})
    with pytest.raises(ReportIntegrityError, match="document"):
        verify_numbers(report.model_copy(update={"documents": [doc]}))


def test_not_applicable_with_a_rate_fails() -> None:
    report = make_report(SOURCE, [], checked=0)
    dim = report.dimensions[0].model_copy(update={"clean_rate": 1.0})
    with pytest.raises(ReportIntegrityError):
        verify_numbers(report.model_copy(update={"dimensions": [dim]}))


def test_verify_report_checks_quotes_against_source_bytes(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# A\n\nUsers need a button.\n", encoding="utf-8")
    loaded = load_source(path, tier=Tier.T4, kind=EvidenceKind.DOCUMENTARY, forced=None)
    findings = [make_finding(evidence=_span(loaded.source, "button"))]
    report = make_report(loaded.source, findings, checked=2)
    verify_report(report, {loaded.source.id: loaded.source})  # honest: passes

    row = report.dimensions[0].findings[0].model_copy(update={"quote": "buttons"})
    dim = report.dimensions[0].model_copy(update={"findings": [row]})
    with pytest.raises(ReportIntegrityError, match="quote"):
        verify_report(
            report.model_copy(update={"dimensions": [dim]}), {loaded.source.id: loaded.source}
        )


def test_verify_report_fails_when_the_file_changed_after_ingest(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# A\n\nUsers need a button.\n", encoding="utf-8")
    loaded = load_source(path, tier=Tier.T4, kind=EvidenceKind.DOCUMENTARY, forced=None)
    report = make_report(loaded.source, [make_finding(evidence=_span(loaded.source, "button"))])
    path.write_text("# A\n\nUsers need a different thing.\n", encoding="utf-8")
    with pytest.raises(ReportIntegrityError, match="re-extract"):
        verify_report(report, {loaded.source.id: loaded.source})


def test_verify_report_fails_on_an_unknown_source() -> None:
    with pytest.raises(ReportIntegrityError, match="source"):
        verify_report(_report(), {})


def _span(source, phrase):  # type: ignore[no-untyped-def]
    return span_of(source, phrase)
