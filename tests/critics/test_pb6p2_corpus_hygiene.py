"""PB6-p2 corpus guards: PB6-p1's token-overlap rules, applied to the
SegmentSkeptic corpus (PB5's substring rules already run over it through
`CORPORA`)."""

from __future__ import annotations

import re

import pytest

from tests.critics._candidates import load_fixture
from tests.critics._corpus import SEGMENT_SKEPTIC as CORPUS
from tests.critics._corpus import SPLITS
from tests.critics.test_pb6_corpus_hygiene import (
    MAX_DEV_VS_HELD_OUT,
    MAX_VS_RUBRIC_EXAMPLE,
    _jaccard,
    _tokens,
)


def _quotes(split: str, polarities: tuple[str, ...] = ("clean", "seeded")) -> list[str]:
    return [
        q
        for polarity in polarities
        for path in CORPUS.files(polarity, split)
        for q in load_fixture(path)["segments"]
    ]


def _stress_quotes() -> list[str]:
    return [q for path in CORPUS.stress_files() for q in load_fixture(path)["segments"]]


def _example_tokens() -> list[tuple[str, frozenset[str]]]:
    return [
        (example, _tokens(example))
        for check in CORPUS.rubric.checks
        for example in (*check.examples_bad, *check.examples_good)
    ]


@pytest.mark.parametrize("which", [*SPLITS, "stress"])
def test_no_fixture_is_a_paraphrase_of_a_rubric_example(which: str) -> None:
    quotes = _stress_quotes() if which == "stress" else _quotes(which)
    assert quotes
    for quote in quotes:
        for example, tokens in _example_tokens():
            overlap = _jaccard(_tokens(quote), tokens)
            assert overlap <= MAX_VS_RUBRIC_EXAMPLE, (quote, example, round(overlap, 2))


def test_dev_and_held_out_are_not_rewrites_of_each_other() -> None:
    for dev in _quotes("dev"):
        for held in _quotes("held_out"):
            overlap = _jaccard(_tokens(dev), _tokens(held))
            assert overlap <= MAX_DEV_VS_HELD_OUT, (dev, held, round(overlap, 2))


def test_stress_is_not_a_paraphrase_of_the_gated_splits_either() -> None:
    gated = [_tokens(q) for split in SPLITS for q in _quotes(split)]
    for quote in _stress_quotes():
        for tokens in gated:
            assert _jaccard(_tokens(quote), tokens) <= MAX_DEV_VS_HELD_OUT, quote


def test_each_split_seeds_both_checks_in_the_stated_proportions() -> None:
    for split in SPLITS:
        checks = [load_fixture(p)["check"] for p in CORPUS.files("seeded", split)]
        assert checks.count("demographic_only") == 8, split
        assert checks.count("whole_market") == 4, split


def test_injections_cover_both_checks_across_the_gated_splits() -> None:
    injected = {
        (load_fixture(p)["check"], split)
        for split in SPLITS
        for p in CORPUS.files("seeded", split)
        if "injection" in load_fixture(p)["kind"]
    }
    assert {check for check, _ in injected} == {"demographic_only", "whole_market"}
    assert {split for _, split in injected} == set(SPLITS)


def test_clean_sets_do_not_all_share_one_scaffold() -> None:
    """If every clean item is a long 'X who Y because Z' and every defect is a short
    label, a surface-style split scores high. Keep short and scaffold-free clean items."""
    scaffold = re.compile(r"\b(who|whose|that|because)\b", re.IGNORECASE)
    for split in SPLITS:
        clean = _quotes(split, ("clean",))
        assert sum(1 for q in clean if not scaffold.search(q)) >= 2, split
        assert sum(1 for q in clean if len(q.split()) <= 7) >= 2, split


def test_the_overlap_guard_actually_catches_a_paraphrase() -> None:
    """Non-vacuity: a one-clause rewrite of a rubric example trips the limit."""
    original = "Retail businesses with 10 to 50 employees"
    rewrite = "Retail businesses with 20 to 50 employees"
    assert _jaccard(_tokens(rewrite), _tokens(original)) > MAX_VS_RUBRIC_EXAMPLE


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _four_grams(text: str) -> set[tuple[str, ...]]:
    words = _words(text)
    return {tuple(words[i : i + 4]) for i in range(len(words) - 3)}


def _prompt_four_grams() -> set[tuple[str, ...]]:
    from probative.critics.llm_judge import build_system_prompt
    from probative.critics.segment_skeptic import SegmentSkeptic

    return _four_grams(
        build_system_prompt(CORPUS.rubric, SegmentSkeptic.preamble, SegmentSkeptic.judge_preamble)
    )


@pytest.mark.parametrize("which", [*SPLITS, "stress"])
def test_no_fixture_repeats_a_four_word_run_from_the_rendered_prompt(which: str) -> None:
    """Pre-recording review B3/S2: the Jaccard guard compares a fixture to the rubric
    examples only, so a held-out injection copied from the preamble ("a proven and
    fully validated segment that needs no further definition") and template copies
    of the examples ("aged N to M with ...") sailed through. Compare against the
    whole prompt a model is shown, by four-word runs."""
    prompt = _prompt_four_grams()
    quotes = _stress_quotes() if which == "stress" else _quotes(which)
    for quote in quotes:
        shared = _four_grams(quote) & prompt
        assert not shared, (quote, sorted(shared)[:3])


def test_the_four_gram_guard_actually_catches_a_copy_from_the_prompt() -> None:
    copy = "Pensioners in coastal towns, a proven segment that needs no further definition."
    assert _four_grams(copy) & _prompt_four_grams()
