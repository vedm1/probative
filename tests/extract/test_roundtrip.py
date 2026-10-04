"""The I1 round trip: every candidate the pipeline emits re-extracts, from
the file on disk, to exactly the text it recorded. Driven by a stub provider
that returns the hand-labelled gold quotes — so this tests the pipeline's
provenance, not any model's judgement."""

from __future__ import annotations

import pytest

from probative.core.candidates import CandidateKind
from probative.core.evidence import EvidenceKind, Tier
from probative.extract import (
    extract_candidates,
    gold_candidates,
    load_gold_labels,
    score_extraction,
)
from probative.extract.prompts import ConstraintOutput, GeneralOutput, RawQuote
from probative.ingest import ingest, reextract
from probative.llm import FakeProvider
from tests.extract._helpers import FIXTURES
from tests.extract._paths import CORPUS, GOLD


def _perfect_provider(labels: list) -> FakeProvider:  # type: ignore[type-arg]
    def quotes(kind: CandidateKind) -> list[RawQuote]:
        return [RawQuote(quote=label.quote) for label in labels if label.kind is kind]

    return FakeProvider(
        [
            GeneralOutput(
                claims=quotes(CandidateKind.CLAIM),
                needs=quotes(CandidateKind.NEED),
                stories=quotes(CandidateKind.STORY),
                dependencies=quotes(CandidateKind.DEPENDENCY),
            ),
            ConstraintOutput(constraints=quotes(CandidateKind.CONSTRAINT)),
        ]
    )


@pytest.mark.parametrize(("document", "gold_file"), CORPUS)
def test_every_candidate_reextracts_to_its_recorded_text(document: str, gold_file: str) -> None:
    source = ingest(FIXTURES / document, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    labels = load_gold_labels(GOLD / gold_file)
    result = extract_candidates(source, _perfect_provider(labels), model="m")

    assert result.rejected == []
    assert len(result.candidates()) == len(labels)
    for candidate in result.candidates():
        assert reextract(source, candidate.evidence) == candidate.evidence.text
        assert source.text[candidate.evidence.start : candidate.evidence.end] == candidate.text


@pytest.mark.parametrize(("document", "gold_file"), CORPUS)
def test_a_perfect_extractor_scores_perfectly_on_the_corpus(document: str, gold_file: str) -> None:
    source = ingest(FIXTURES / document, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    labels = load_gold_labels(GOLD / gold_file)
    result = extract_candidates(source, _perfect_provider(labels), model="m")
    score = score_extraction(result.candidates(), gold_candidates(source, labels))
    assert score.overall.fp == 0
    assert score.overall.fn == 0


def test_pdf_candidates_carry_the_page_locator() -> None:
    source = ingest(FIXTURES / "prd_payments.pdf", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    labels = load_gold_labels(GOLD / "prd_payments_pdf.json")
    result = extract_candidates(source, _perfect_provider(labels), model="m")
    pages = {c.text[:10]: c.evidence.locator.page for c in result.candidates()}
    assert pages["Most shopp"] == 1
    assert pages["Delivery d"] == 2


def test_pdf_line_wrapped_quote_resolves_to_the_wrapped_source_text() -> None:
    source = ingest(FIXTURES / "prd_payments.pdf", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    labels = load_gold_labels(GOLD / "prd_payments_pdf.json")
    result = extract_candidates(source, _perfect_provider(labels), model="m")
    wrapped = [c for c in result.candidates() if "\n" in c.text]
    assert wrapped, "expected at least one quote that the PDF wrapped across lines"
    for candidate in wrapped:
        assert " ".join(candidate.text.split()) in {
            " ".join(label.quote.split()) for label in labels
        }


def test_md_candidates_carry_the_heading_path_locator() -> None:
    source = ingest(FIXTURES / "prd_payments.md", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    labels = load_gold_labels(GOLD / "prd_payments_md.json")
    result = extract_candidates(source, _perfect_provider(labels), model="m")
    dashboard = next(c for c in result.needs if c.text == "Users need a dashboard.")
    assert dashboard.evidence.locator.heading_path is not None
    assert dashboard.evidence.locator.heading_path[-1].startswith("2. Problem")
