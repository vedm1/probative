from __future__ import annotations

import pytest

from probative.core.critic import Severity
from probative.core.evidence import Locator
from probative.critique.report import (
    ReportIntegrityError,
    locator_label,
    report_finding,
)
from tests.critique._builders import make_finding, make_source, span_of

TEXT = "# Goals\n\nUsers need a one-click checkout button. Conversion is 73% lower today.\n"


def test_locator_label_forms() -> None:
    assert locator_label(Locator(page=4, line=12)) == "p.4 · line 12"
    assert locator_label(Locator(line=3, heading_path=["A", "B"])) == "line 3 · A > B"
    assert locator_label(Locator(sheet="Sheet1", cell="B7")) == "Sheet1!B7"
    assert locator_label(Locator(issue_key="DEMO-1", field="Description")) == "DEMO-1 · Description"
    assert locator_label(Locator()) == "location unknown"


def test_report_finding_carries_quote_offsets_and_context() -> None:
    source = make_source(TEXT)
    span = span_of(source, "one-click checkout button")
    rf = report_finding(make_finding(evidence=span), source)
    assert rf.quote == "one-click checkout button"
    assert source.text[rf.start : rf.end] == rf.quote
    assert rf.context_before.endswith("Users need a ")
    assert rf.context_after.startswith(". Conversion")
    assert rf.locator_label == "line 3"
    assert rf.source_id == source.id
    assert rf.severity is Severity.BLOCK


def test_context_is_clipped_at_word_boundaries() -> None:
    body = "alpha " * 200 + "TARGET" + " omega" * 200
    source = make_source(body)
    rf = report_finding(make_finding(evidence=span_of(source, "TARGET")), source)
    assert len(rf.context_before) <= 240 and len(rf.context_after) <= 240
    assert rf.context_clipped_before and rf.context_clipped_after
    assert not rf.context_before.startswith("lpha")  # no half word
    assert source.text[: rf.start].endswith(rf.context_before)
    assert source.text[rf.end :].startswith(rf.context_after)


def test_finding_without_evidence_is_an_integrity_error() -> None:
    source = make_source(TEXT)
    with pytest.raises(ReportIntegrityError, match="evidence"):
        report_finding(make_finding(evidence=None), source)


def test_finding_without_target_is_an_integrity_error() -> None:
    source = make_source(TEXT)
    span = span_of(source, "73%")
    with pytest.raises(ReportIntegrityError, match="target"):
        report_finding(make_finding(evidence=span, target_id=None), source)


def test_quote_that_is_not_the_source_text_is_an_integrity_error() -> None:
    source = make_source(TEXT)
    span = span_of(source, "73%").model_copy(update={"text": "74%"})
    with pytest.raises(ReportIntegrityError, match="quote"):
        report_finding(make_finding(evidence=span), source)


def test_span_from_another_source_is_an_integrity_error() -> None:
    source = make_source(TEXT)
    span = span_of(source, "73%").model_copy(update={"source_id": "src_other"})
    with pytest.raises(ReportIntegrityError, match="source"):
        report_finding(make_finding(evidence=span), source)
