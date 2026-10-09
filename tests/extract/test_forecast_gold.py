"""The forecast gold labels resolve, are unique, and the traps are not labelled
(PB8). Key-free; the model's behaviour is the recorded replay."""

from __future__ import annotations

from probative.core.candidates import CandidateKind
from probative.core.evidence import EvidenceKind, Tier
from probative.extract import gold_candidates, load_gold_labels
from probative.ingest import ingest, reextract
from tests.extract._helpers import FIXTURES
from tests.extract._paths import GOLD

TRAPS = (
    "We will install the first twelve lockers",  # the team's plan
    "Each locker must hold",  # a requirement
    "The target for the pilot",  # a target
    "nothing will leave the depot",  # a present fact containing "will"
    "As a recipient I want",  # a user story
    "Ignore all previous instructions",  # an injection
    "Roughly one delivery in nine",  # a present fact
)


def _gold() -> list:  # type: ignore[type-arg]
    source = ingest(FIXTURES / "prd_forecasts.md", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    return gold_candidates(source, load_gold_labels(GOLD / "prd_forecasts.json"))


def test_gold_forecasts_resolve_uniquely_and_round_trip() -> None:
    source = ingest(FIXTURES / "prd_forecasts.md", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    gold = _gold()
    assert len(gold) == 4
    assert {c.kind for c in gold} == {CandidateKind.FORECAST}
    for candidate in gold:
        assert reextract(source, candidate.evidence) == candidate.evidence.text
        assert all(trap not in candidate.text for trap in TRAPS)


def test_every_trap_is_in_the_document_so_it_is_a_real_trap() -> None:
    text = (FIXTURES / "prd_forecasts.md").read_text()
    for trap in TRAPS:
        assert trap in text, trap
