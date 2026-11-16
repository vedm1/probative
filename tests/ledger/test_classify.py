from __future__ import annotations

import pytest

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.ledger.classify import (
    CUES,
    MARKET_CUES,
    Classification,
    Unclassified,
    classify_source,
)

MD = SourceFormat.MARKDOWN


@pytest.mark.parametrize(("cue", "kind"), sorted(CUES.items()))
def test_each_cue_gives_a_t1_classification(cue: str, kind: EvidenceKind) -> None:
    got = classify_source(f"{cue}/notes.md", MD)
    assert got == Classification(Tier.T1, kind, f"cue:{cue}")


def test_a_cue_is_matched_case_insensitively_on_any_directory_level() -> None:
    got = classify_source("acme/Interviews/2026/round1/a.md", MD)
    assert isinstance(got, Classification) and got.kind is EvidenceKind.CUSTOMER


def test_the_file_name_is_not_a_cue() -> None:
    assert isinstance(classify_source("interviews.md", MD), Unclassified)


def test_two_cues_that_disagree_are_unclassified() -> None:
    got = classify_source("interviews/sop/a.md", MD)
    assert isinstance(got, Unclassified) and "conflict" in got.reason


def test_two_cues_that_agree_are_fine() -> None:
    got = classify_source("interviews/reviews/a.md", MD)
    assert isinstance(got, Classification) and got.kind is EvidenceKind.CUSTOMER


@pytest.mark.parametrize("cue", sorted(MARKET_CUES))
def test_market_material_is_never_classified_because_t2_needs_a_url(cue: str) -> None:
    got = classify_source(f"{cue}/report.md", MD)
    assert isinstance(got, Unclassified) and "T2" in got.reason and "PB15" in got.reason


def test_a_market_cue_wins_over_a_customer_cue() -> None:
    assert isinstance(classify_source("research/interviews/a.md", MD), Unclassified)


def test_no_cue_is_unclassified() -> None:
    got = classify_source("misc/notes.md", MD)
    assert isinstance(got, Unclassified) and "no" in got.reason


@pytest.mark.parametrize(
    "fmt",
    [SourceFormat.JIRA_CSV, SourceFormat.JIRA_HTML, SourceFormat.JIRA_XML, SourceFormat.ADO_CSV],
)
def test_a_tracker_export_with_no_cue_defaults_to_delivery(fmt: SourceFormat) -> None:
    assert classify_source("export.csv", fmt) == Classification(
        Tier.T1, EvidenceKind.DELIVERY, "format:tracker"
    )


def test_a_tracker_export_in_a_support_folder_is_customer_evidence() -> None:
    got = classify_source("support/export.csv", SourceFormat.JIRA_CSV)
    assert isinstance(got, Classification) and got.kind is EvidenceKind.CUSTOMER


def test_a_confluence_export_with_no_cue_defaults_to_documentary() -> None:
    assert classify_source("space.doc", SourceFormat.CONFLUENCE_WORD) == Classification(
        Tier.T1, EvidenceKind.DOCUMENTARY, "format:confluence"
    )


def test_the_classifier_can_never_return_t2_to_t5() -> None:
    for cue in CUES:
        got = classify_source(f"{cue}/x.md", MD)
        assert isinstance(got, Classification) and got.tier is Tier.T1
    assert all(isinstance(v, EvidenceKind) for v in CUES.values())


def test_the_cue_words_and_the_market_words_do_not_overlap() -> None:
    assert not set(CUES) & MARKET_CUES


def test_classification_is_deterministic() -> None:
    assert classify_source("ops/logs/a.md", MD) == classify_source("ops/logs/a.md", MD)
