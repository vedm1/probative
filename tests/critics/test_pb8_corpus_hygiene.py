"""PB8 corpus guards, same discipline as PB6/PB7 (see test_pb6_corpus_hygiene):
token-overlap against the rubric's examples and between splits, four-word runs
against the rendered prompt, bare declaratives in the clean sets, and the shape
of the seeded set (three per mode per split, injections on two modes in two
forms)."""

from __future__ import annotations

import re

import pytest

from probative.critics.llm_judge import build_system_prompt
from probative.critics.red_team import RedTeam
from tests.critics._candidates import load_fixture
from tests.critics._corpus import RED_TEAM as CORPUS
from tests.critics._corpus import SPLITS

MAX_VS_RUBRIC_EXAMPLE = 0.4
MAX_DEV_VS_HELD_OUT = 0.3
CHECKS = (
    "rival_explanation",
    "unstated_denominator",
    "definition_drift",
    "unstated_precondition",
    "no_adaptive_response",
    "unfalsifiable_outcome",
)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b)


def _statements(data: dict[str, object]) -> list[str]:
    out: list[str] = []
    for key in ("claims", "forecasts"):
        out.extend(data.get(key, []))  # type: ignore[arg-type, call-overload]
    return out


def _quotes(split: str, polarities: tuple[str, ...] = ("clean", "seeded")) -> list[str]:
    return [
        q
        for polarity in polarities
        for path in CORPUS.files(polarity, split)
        for q in _statements(load_fixture(path))
    ]


def _stress_quotes() -> list[str]:
    return [q for path in CORPUS.stress_files() for q in _statements(load_fixture(path))]


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
            assert _jaccard(_tokens(quote), tokens) <= 0.5, quote


def _template(text: str) -> tuple[str, ...]:
    """The opening three words: a structural copy keeps its template."""
    return tuple(re.findall(r"[a-z0-9]+", text.lower())[:3])


@pytest.mark.parametrize("which", [*SPLITS, "stress"])
def test_no_fixture_opens_like_a_rubric_example(which: str) -> None:
    """Pre-recording review B6: Jaccard passes a template copy ("X rose in March, which
    shows ..."), so also compare openings."""
    quotes = _stress_quotes() if which == "stress" else _quotes(which)
    openings = {_template(e) for e, _ in _example_tokens()}
    for quote in quotes:
        assert _template(quote) not in openings, quote


def test_the_guard_actually_catches_a_paraphrase() -> None:
    original = "Refund requests rose in March, which shows the redesigned receipt confuses buyers"
    rewrite = "Refund requests rose in April, which shows the redesigned receipt confuses buyers"
    assert _jaccard(_tokens(rewrite), _tokens(original)) > MAX_VS_RUBRIC_EXAMPLE


@pytest.mark.parametrize("split", SPLITS)
def test_three_seeded_defects_per_mode_per_split_and_one_statement_each(split: str) -> None:
    per_check: dict[str, int] = {check: 0 for check in CHECKS}
    for path in CORPUS.files("seeded", split):
        data = load_fixture(path)
        assert len(_statements(data)) == 1, path.name
        per_check[data["check"]] += 1
    assert per_check == {check: 3 for check in CHECKS}


@pytest.mark.parametrize("split", SPLITS)
def test_forecast_modes_are_seeded_on_forecasts_and_claim_modes_on_claims(split: str) -> None:
    claim_modes = set(CHECKS[:3])
    for path in CORPUS.files("seeded", split):
        data = load_fixture(path)
        field = "claims" if data["check"] in claim_modes else "forecasts"
        assert data.get(field) and not data.get("claims" if field == "forecasts" else "forecasts")


def test_injections_are_on_two_modes_in_two_forms_across_the_gated_splits() -> None:
    found: dict[str, set[str]] = {}
    for split in SPLITS:
        for path in CORPUS.files("seeded", split):
            data = load_fixture(path)
            if "injection" in data["kind"]:
                found.setdefault(data["check"], set()).add(data["kind"])
    assert set(found) == {"rival_explanation", "unfalsifiable_outcome"}
    assert len({kind for kinds in found.values() for kind in kinds}) >= 3


def test_each_clean_split_has_bare_declaratives_with_no_lexical_marker() -> None:
    """If every clean item spells out a base, a condition or a definition and every
    defect is bare, a surface-style split scores high. Keep bare declaratives in the
    clean sets."""
    marker = re.compile(
        r"\bif\b|provided|assuming|unless|even if|hypothes|\bbet\b|test|holdout|compared|"
        r"matched|at least|\bof\b|against|=|expect|\bafter\b|\bbecause\b",
        re.IGNORECASE,
    )
    for split in SPLITS:
        bare = [q for q in _quotes(split, ("clean",)) if not marker.search(q)]
        assert len(bare) >= 3, (split, bare)


def _four_grams(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(words[i : i + 4]) for i in range(len(words) - 3)}


def test_no_gated_statement_repeats_a_four_word_run_from_the_rendered_prompt() -> None:
    prompt = _four_grams(
        build_system_prompt(CORPUS.rubric, RedTeam.preamble, RedTeam.judge_preamble)
    )
    for split in SPLITS:
        for quote in _quotes(split):
            assert not _four_grams(quote) & prompt, quote


def test_stress_fixtures_name_what_they_expect() -> None:
    for path in CORPUS.stress_files():
        data = load_fixture(path)
        assert set(data["expect_fired"]) | set(data["allow_also"]) <= set(CHECKS), path.name
        assert data["why"], path.name
