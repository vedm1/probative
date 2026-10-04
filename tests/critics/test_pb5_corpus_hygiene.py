"""The PB5 fixture corpora are held to rules that keep the measured numbers
honest (OI17): no fixture is a rubric example, dev and held-out never share a
sentence, and a defect file holds exactly one candidate."""

from __future__ import annotations

import re

import pytest

from probative.critics.rubric import resolve_fixture_paths
from tests.critics._candidates import fixture_source, load_fixture
from tests.critics._corpus import CORPORA, SPACE_WARDEN, SPLITS, Corpus


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text).strip().lower()


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_rubric_globs_find_every_fixture(corpus: Corpus) -> None:
    clean, defect = resolve_fixture_paths(corpus.rubric, corpus.rubric_path)
    assert clean == sorted(p for s in SPLITS for p in corpus.files("clean", s))
    assert defect == sorted(p for s in SPLITS for p in corpus.files("seeded", s))
    assert clean and defect


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
@pytest.mark.parametrize("split", SPLITS)
def test_every_split_has_both_polarities(corpus: Corpus, split: str) -> None:
    assert corpus.files("clean", split)
    assert len(corpus.files("seeded", split)) >= 12


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
@pytest.mark.parametrize("split", SPLITS)
def test_a_defect_file_holds_exactly_one_candidate_and_names_a_real_check(
    corpus: Corpus, split: str
) -> None:
    check_ids = {c.id for c in corpus.rubric.checks}
    for path in corpus.files("seeded", split):
        data = load_fixture(path)
        assert len(data[corpus.candidate_key]) == 1, path
        assert data["check"] in check_ids, path
        assert len(corpus.parse(path)) == 1


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_every_check_is_seeded_in_both_splits(corpus: Corpus) -> None:
    if corpus is SPACE_WARDEN:
        return  # one check; its defect kinds are covered below
    for split in SPLITS:
        seeded = {load_fixture(p)["check"] for p in corpus.files("seeded", split)}
        assert seeded == {c.id for c in corpus.rubric.checks}, split


def test_space_warden_seeds_every_defect_kind_in_both_splits() -> None:
    kinds = {"feature_name", "ui_element", "implementation", "technology", "smuggled", "injection"}
    for split in SPLITS:
        got = {load_fixture(p)["defect"] for p in SPACE_WARDEN.files("seeded", split)}
        assert got == kinds, split


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_no_fixture_candidate_is_a_rubric_example(corpus: Corpus) -> None:
    """A critic shown a sentence in its prompt and then tested on it measures
    nothing."""
    examples = {_norm(e) for c in corpus.rubric.checks for e in (*c.examples_bad, *c.examples_good)}
    for polarity in ("clean", "seeded"):
        for split in SPLITS:
            for path in corpus.files(polarity, split):
                for quote in load_fixture(path)[corpus.candidate_key]:
                    norm = _norm(quote)
                    assert not any(ex in norm for ex in examples if ex), (path, quote)


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_dev_and_held_out_share_no_candidate(corpus: Corpus) -> None:
    def quotes(split: str) -> set[str]:
        return {
            _norm(q)
            for polarity in ("clean", "seeded")
            for path in corpus.files(polarity, split)
            for q in load_fixture(path)[corpus.candidate_key]
        }

    assert quotes("dev").isdisjoint(quotes("held_out"))


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_every_fixture_candidate_resolves_and_round_trips_to_its_source(corpus: Corpus) -> None:
    for polarity in ("clean", "seeded"):
        for split in SPLITS:
            for path in corpus.files(polarity, split):
                source = fixture_source(path)
                for candidate in corpus.parse(path):
                    ev = candidate.evidence  # type: ignore[attr-defined]
                    assert source.text[ev.start : ev.end] == ev.text


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_stress_cases_are_outside_the_s2_globs_and_well_formed(corpus: Corpus) -> None:
    clean, defect = resolve_fixture_paths(corpus.rubric, corpus.rubric_path)
    stress = corpus.stress_files()
    assert len(stress) >= 9
    assert not set(stress) & set(clean + defect)  # borderline cases cannot gate S2
    check_ids = {c.id for c in corpus.rubric.checks}
    for path in stress:
        data = load_fixture(path)
        assert set(data["expect_fired"]) <= check_ids, path.name
        assert data["why"], path.name
        assert corpus.parse(path), path.name


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_stress_cases_share_nothing_with_the_gated_splits_or_the_rubric_examples(
    corpus: Corpus,
) -> None:
    gated = {
        _norm(q)
        for polarity in ("clean", "seeded")
        for split in SPLITS
        for path in corpus.files(polarity, split)
        for q in load_fixture(path)[corpus.candidate_key]
    }
    examples = {_norm(e) for c in corpus.rubric.checks for e in (*c.examples_bad, *c.examples_good)}
    for path in corpus.stress_files():
        for quote in load_fixture(path)[corpus.candidate_key]:
            assert _norm(quote) not in gated, path.name
            assert not any(ex in _norm(quote) for ex in examples if ex), path.name
