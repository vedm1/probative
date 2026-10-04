"""PB6-p1 corpus guards beyond PB5's substring checks.

PB5's `test_no_fixture_candidate_is_a_rubric_example` only catches a fixture
that *contains* a rubric example verbatim. The PB6 pre-recording review found
a domain-swapped held-out set and one-clause rewrites of the rubric examples
sailed through it. These guards compare token sets, which catches a paraphrase.

The thresholds are measured limits, not round numbers: on the committed corpus
the largest fixture-vs-example overlap and the largest dev-vs-held-out overlap
sit well below them. A change that pushes either past its limit is a near-copy.
"""

from __future__ import annotations

import re

import pytest

from tests.critics._candidates import load_fixture
from tests.critics._corpus import EVIDENCE_AUDITOR as CORPUS
from tests.critics._corpus import SPLITS

MAX_VS_RUBRIC_EXAMPLE = 0.4
MAX_DEV_VS_HELD_OUT = 0.3


def _tokens(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b)


def _quotes(split: str, polarities: tuple[str, ...] = ("clean", "seeded")) -> list[str]:
    return [
        q
        for polarity in polarities
        for path in CORPUS.files(polarity, split)
        for q in load_fixture(path)["claims"]
    ]


def _stress_quotes() -> list[str]:
    return [q for path in CORPUS.stress_files() for q in load_fixture(path)["claims"]]


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


def test_the_guard_actually_catches_a_paraphrase() -> None:
    """Non-vacuity: a one-clause rewrite of a rubric example trips the limit."""
    original = "62% of mid-market CFOs say reconciliation is their biggest time sink"
    rewrite = "58% of mid-market CFOs say reconciliation is their biggest time drain"
    assert _jaccard(_tokens(rewrite), _tokens(original)) > MAX_VS_RUBRIC_EXAMPLE


def test_each_clean_split_has_bare_declaratives_with_no_lexical_marker() -> None:
    """The reviewer's point: if every clean item carries a marker ("[3]",
    "According to", "Assumption:") and every defect is bare, a surface-style
    split scores high. Keep bare declaratives in the clean sets."""
    marker = re.compile(
        r"[\[\(¹²³]|according to|assum|hypothes|believe|bet is|target|panel|pilot|trial|"
        r"found that|\bour\b|calculated|means the",
        re.IGNORECASE,
    )
    for split in SPLITS:
        bare = [q for q in _quotes(split, ("clean",)) if not marker.search(q)]
        assert len(bare) >= 3, (split, bare)


def _four_grams(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(words[i : i + 4]) for i in range(len(words) - 3)}


def test_no_gated_claim_repeats_a_four_word_run_from_the_rendered_prompt() -> None:
    """The p2 review found the Jaccard guard blind to a fixture copied from the
    preamble; the same check on p1's gated splits is clean. Stress is exempt and one
    case is known to violate it: `stress/form_minutes.json` ("takes about six
    minutes") is the judge preamble's own worked example. It is non-gating, and
    rewording it would stale the recorded stress run, so it is documented rather than
    changed."""
    from probative.critics.evidence_auditor import EvidenceAuditor
    from probative.critics.llm_judge import build_system_prompt

    prompt = _four_grams(
        build_system_prompt(CORPUS.rubric, EvidenceAuditor.preamble, EvidenceAuditor.judge_preamble)
    )
    for split in SPLITS:
        for quote in _quotes(split):
            assert not _four_grams(quote) & prompt, quote


def test_the_known_stress_exception_is_exactly_the_one_documented() -> None:
    from probative.critics.evidence_auditor import EvidenceAuditor
    from probative.critics.llm_judge import build_system_prompt

    prompt = _four_grams(
        build_system_prompt(CORPUS.rubric, EvidenceAuditor.preamble, EvidenceAuditor.judge_preamble)
    )
    offenders = {
        path.stem
        for path in CORPUS.stress_files()
        for q in load_fixture(path)["claims"]
        if _four_grams(q) & prompt
    }
    assert offenders == {"form_minutes"}
