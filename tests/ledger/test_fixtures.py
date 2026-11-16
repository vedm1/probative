"""Hygiene for the synthetic judge fixtures, and a key-free measurement of the
pre-filter: how many seeded contradictions are even offered to the judge."""

from __future__ import annotations

import pytest

from probative.core.evidence import Tier
from probative.core.graph.graph import Graph
from probative.critics.rubric import load_rubric, resolve_fixture_paths
from probative.ledger.build import new_claim
from probative.ledger.contradict import RUBRIC_PATH, candidate_pairs
from tests.ledger import _pairs
from tests.ledger._helpers import NOW, OWNER

SPLITS = ("dev", "held_out")


def offered(pair: _pairs.Pair) -> bool:
    a = new_claim(pair.a, Tier.T1, None, owner=OWNER, now=NOW)
    b = new_claim(pair.b, Tier.T1, None, owner=OWNER, now=NOW)
    return bool(candidate_pairs(Graph.empty().with_patch(nodes=[a, b]), 10).pairs)


def test_the_rubric_globs_resolve_to_the_fixture_files() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    clean, defect = resolve_fixture_paths(rubric, RUBRIC_PATH)
    assert [p.parent.name for p in clean] == ["consistent"]
    assert [p.parent.name for p in defect] == ["contradicting"]


def test_the_fixture_sizes_are_the_spec_sizes() -> None:
    for split in SPLITS:
        assert len(_pairs.contradicting(split)) == 12
        assert len(_pairs.consistent(split)) == 12
        assert len(_pairs.consistent(split, hard=True)) == 4
    assert len(_pairs.stress()) == 8


def test_ids_are_unique_and_no_pair_repeats_across_dev_and_held_out() -> None:
    every = [p for s in (*SPLITS, "stress") for p in _pairs.split(s)]
    assert len({p.id for p in every}) == len(every)
    dev = {frozenset((p.a, p.b)) for p in _pairs.split("dev")}
    held = {frozenset((p.a, p.b)) for p in _pairs.split("held_out")}
    assert not dev & held


def test_a_statement_is_never_a_pair_with_itself_except_the_one_stress_case() -> None:
    same = [p.id for s in (*SPLITS, "stress") for p in _pairs.split(s) if p.a == p.b]
    assert same == ["s04"]


@pytest.mark.parametrize("split", SPLITS)
def test_the_judge_set_for_a_split_is_balanced(split: str) -> None:
    assert len(_pairs.contradicting(split)) == len(_pairs.consistent(split))


def test_the_pre_filter_misses_just_under_half_of_the_seeded_contradictions() -> None:
    """A measured weakness, pinned so it cannot change unseen (OI44, owner decision pending).

    The spec's rule (3 shared content words, or Jaccard 0.25) offers 13 of the 24 seeded
    contradictions to the judge and drops 11, because those pairs share one word or none
    ("Refunds are issued automatically within one hour." / "Refunds must be requested
    manually by a support agent."). Sharing one stemmed word would offer 22 of 24, but would
    offer about 11% of all pairs of statements to the judge. A change to the rule changes
    this list: update it on purpose, with the numbers."""
    missed = sorted(p.id for s in SPLITS for p in _pairs.contradicting(s) if not offered(p))
    assert missed == [
        "cd04", "cd05", "cd07", "cd10", "cd12",
        "ch02", "ch04", "ch05", "ch06", "ch09", "ch11",
    ]  # fmt: skip
