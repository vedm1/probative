"""Precision/recall (extract/scoring.py), checked against cases worked by
hand. These are eval metrics, not node fields — see PB4 spec, Scoring."""

from __future__ import annotations

import pytest

from probative.core.candidates import (
    Candidate,
    CandidateKind,
    ClaimCandidate,
    NeedCandidate,
    candidate_id,
)
from probative.core.evidence import EvidenceSpan, Locator
from probative.extract.scoring import score_extraction


def _cand(kind: CandidateKind, start: int, end: int) -> Candidate:
    span = EvidenceSpan(
        source_id="s", start=start, end=end, text="x" * (end - start), locator=Locator()
    )
    cls = {CandidateKind.CLAIM: ClaimCandidate, CandidateKind.NEED: NeedCandidate}[kind]
    return cls(id=candidate_id(kind, span), evidence=span)


CLAIM, NEED = CandidateKind.CLAIM, CandidateKind.NEED


def test_perfect_match() -> None:
    gold = [_cand(NEED, 0, 10), _cand(NEED, 20, 30)]
    score = score_extraction(list(gold), gold)
    assert (score.overall.tp, score.overall.fp, score.overall.fn) == (2, 0, 0)
    assert score.overall.precision == 1.0
    assert score.overall.recall == 1.0


def test_worked_example_one_miss_one_spurious() -> None:
    # gold: 3 needs. predicted: 2 hit, 1 spurious -> TP=2 FP=1 FN=1.
    gold = [_cand(NEED, 0, 10), _cand(NEED, 20, 30), _cand(NEED, 40, 50)]
    predicted = [_cand(NEED, 0, 10), _cand(NEED, 20, 30), _cand(NEED, 60, 70)]
    score = score_extraction(predicted, gold)
    assert (score.overall.tp, score.overall.fp, score.overall.fn) == (2, 1, 1)
    assert score.overall.precision == pytest.approx(2 / 3)
    assert score.overall.recall == pytest.approx(2 / 3)


def test_iou_exactly_half_matches_just_below_does_not() -> None:
    gold = [_cand(NEED, 0, 10)]
    # overlap 5, union 15 -> IoU 1/3: no match.
    assert score_extraction([_cand(NEED, 5, 15)], gold).overall.tp == 0
    # [0,10) vs [0,5): overlap 5, union 10 -> IoU 0.5: match.
    assert score_extraction([_cand(NEED, 0, 5)], gold).overall.tp == 1
    # [0,10) vs [0,4): IoU 0.4: no match.
    assert score_extraction([_cand(NEED, 0, 4)], gold).overall.tp == 0


def test_matching_is_one_to_one() -> None:
    gold = [_cand(NEED, 0, 10)]
    predicted = [_cand(NEED, 0, 10), _cand(NEED, 0, 9)]
    score = score_extraction(predicted, gold)
    assert (score.overall.tp, score.overall.fp, score.overall.fn) == (1, 1, 0)


def test_best_overlap_wins_the_gold_span() -> None:
    gold = [_cand(NEED, 0, 10)]
    predicted = [_cand(NEED, 0, 6), _cand(NEED, 0, 10)]
    score = score_extraction(predicted, gold)
    assert (score.overall.tp, score.overall.fp) == (1, 1)


def test_kinds_never_match_each_other() -> None:
    gold = [_cand(NEED, 0, 10)]
    predicted = [_cand(CLAIM, 0, 10)]
    score = score_extraction(predicted, gold)
    assert score.per_kind[NEED].fn == 1
    assert score.per_kind[CLAIM].fp == 1
    assert score.overall.tp == 0


def test_undefined_ratios_are_none_not_one() -> None:
    empty = score_extraction([], [])
    assert empty.overall.precision is None
    assert empty.overall.recall is None
    nothing_predicted = score_extraction([], [_cand(NEED, 0, 10)])
    assert nothing_predicted.overall.precision is None
    assert nothing_predicted.overall.recall == 0.0
    nothing_gold = score_extraction([_cand(NEED, 0, 10)], [])
    assert nothing_gold.overall.precision == 0.0
    assert nothing_gold.overall.recall is None


def test_every_kind_is_reported_even_when_absent() -> None:
    score = score_extraction([], [])
    assert set(score.per_kind) == set(CandidateKind)


def test_spans_from_different_sources_never_match() -> None:
    a = _cand(NEED, 0, 10)
    other = NeedCandidate(
        id=candidate_id(
            CandidateKind.NEED,
            EvidenceSpan(source_id="t", start=0, end=10, text="x" * 10, locator=Locator()),
        ),
        evidence=EvidenceSpan(source_id="t", start=0, end=10, text="x" * 10, locator=Locator()),
    )
    assert score_extraction([other], [a]).overall.tp == 0


def test_duplicate_gold_labels_are_an_error() -> None:
    from probative.extract import GoldLabel, GoldLabelError, gold_candidates
    from tests.extract._helpers import make_source

    source = make_source("Users need X.\nOther.\n")
    labels = [GoldLabel(kind=NEED, quote="Users need X.")] * 2
    with pytest.raises(GoldLabelError):
        gold_candidates(source, labels)


def test_gold_quote_with_a_whitespace_variant_elsewhere_is_not_unique() -> None:
    from probative.extract import GoldLabel, GoldLabelError, gold_candidates
    from tests.extract._helpers import make_source

    source = make_source("Users need X.\nUsers  need X.\n")
    with pytest.raises(GoldLabelError, match="unique"):
        gold_candidates(source, [GoldLabel(kind=NEED, quote="Users need X.")])


def test_gold_quote_that_is_not_in_the_document_is_an_error() -> None:
    from probative.extract import GoldLabel, GoldLabelError, gold_candidates
    from tests.extract._helpers import make_source

    with pytest.raises(GoldLabelError, match="not resolvable"):
        gold_candidates(
            make_source("Users need X.\n"), [GoldLabel(kind=NEED, quote="Invented sentence.")]
        )


def test_gold_labels_build_every_candidate_kind() -> None:
    from probative.extract import GoldLabel, gold_candidates
    from tests.extract._helpers import make_source

    source = make_source(
        "Claim one. Need two. Story three. Constraint four. Dependency five. Segment six.\n"
    )
    labels = [
        GoldLabel(kind=kind, quote=quote)
        for kind, quote in zip(
            CandidateKind,
            [
                "Claim one.",
                "Need two.",
                "Story three.",
                "Constraint four.",
                "Dependency five.",
                "Segment six.",
            ],
            strict=True,
        )
    ]
    built = gold_candidates(source, labels)
    assert [c.kind for c in built] == list(CandidateKind)
