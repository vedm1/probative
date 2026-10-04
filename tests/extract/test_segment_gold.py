"""The segment gold labels resolve, are unique, and the traps are not labelled
(PB6-p2). Key-free; the model's behaviour on this document is the recorded
replay (test_replay_segments.py)."""

from __future__ import annotations

from probative.core.candidates import CandidateKind
from probative.core.evidence import EvidenceKind, Tier
from probative.extract import gold_candidates, load_gold_labels
from probative.ingest import ingest, reextract
from tests.extract._helpers import FIXTURES
from tests.extract._paths import GOLD

TRAPS = (
    "As a freelance photographer",  # a user story that names a role
    "Freelancers need to know",  # a need that names a role
    "About four million",  # a group size, not a definition
    "Maria is a 34-year-old",  # one person
    "Ignore all previous instructions",  # an injection
)


def test_gold_segments_resolve_uniquely_and_round_trip() -> None:
    source = ingest(FIXTURES / "prd_segments.md", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    gold = gold_candidates(source, load_gold_labels(GOLD / "prd_segments.json"))
    assert len(gold) == 4
    assert {c.kind for c in gold} == {CandidateKind.SEGMENT}
    for candidate in gold:
        assert reextract(source, candidate.evidence) == candidate.evidence.text
        assert all(trap not in candidate.text for trap in TRAPS)


def test_the_two_sentence_definition_is_one_gold_segment() -> None:
    source = ingest(FIXTURES / "prd_segments.md", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    gold = gold_candidates(source, load_gold_labels(GOLD / "prd_segments.json"))
    assert any(c.text.startswith("Our third group is bookkeepers. They reconcile") for c in gold)


def test_the_candidate_free_memo_has_no_segment_gold() -> None:
    source = ingest(FIXTURES / "memo_logistics.txt", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    assert gold_candidates(source, load_gold_labels(GOLD / "memo_logistics.json")) == []


def test_pb4s_prd_has_no_segment_gold_because_it_defines_no_target_group() -> None:
    """It is the false-positive probe: every segment predicted on it is wrong by
    construction, so a reader must be able to see that nothing in it defines one."""
    source = ingest(FIXTURES / "prd_payments.md", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    gold = gold_candidates(source, load_gold_labels(GOLD / "prd_payments_md.json"))
    assert not [c for c in gold if c.kind is CandidateKind.SEGMENT]
    assert "target customer" not in source.text.lower()
    assert "our primary" not in source.text.lower() and "target segment" not in source.text.lower()
