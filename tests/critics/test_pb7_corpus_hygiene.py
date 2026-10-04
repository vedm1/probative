"""PB7 corpus guards: the PB5/PB6 rules applied to DependencyCritic's statements
(its `Corpus` is also run by PB5's own guards through `CORPORA`) and to
ConstraintCritic's documents, which have their own shape (constraints, stories,
`expect_untraced`).

Thresholds are the PB6 ones. Story scaffolding ("As a ..., I want to ... so that
...") and the stock words of an obligation ("must be ... under the") are not
content, so token comparisons ignore them; otherwise two unrelated stories
would look alike and a real paraphrase would be diluted."""

from __future__ import annotations

import importlib.util
import re
from itertools import pairwise
from pathlib import Path

import pytest

from probative.critics.constraint_critic import ConstraintCritic, build_trace_prompt
from probative.critics.dependency_critic import DependencyCritic
from probative.critics.llm_judge import build_system_prompt
from probative.critics.rubric import resolve_fixture_paths
from tests.critics._candidates import fixture_source, load_fixture
from tests.critics._corpus import DEPENDENCY_CRITIC, SPLITS
from tests.critics._trace_corpus import CONSTRAINT_CRITIC, parse_trace_doc

MAX_VS_RUBRIC_EXAMPLE = 0.4
MAX_BETWEEN_SPLITS = 0.3

_SCAFFOLD_WORDS = """
as a an i want to so that can the of and in be must is are it its for by on at or any every
under per with from has have been not no only than when before after my their our we this
these those who which whose within
"""
SCAFFOLD = frozenset(_SCAFFOLD_WORDS.split())
AUTHORITY = re.compile(
    r"policy|code|act\b|standard|agreement|regulation|rules?\b|charter|contract|order\b|"
    r"licen[cs]e|pledge|guidelines|bylaw|law|requires|set out|clause|directive",
    re.IGNORECASE,
)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _tokens(text: str) -> frozenset[str]:
    return frozenset(w for w in _words(text) if w not in SCAFFOLD)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


_CLAUSE_BREAK = re.compile(r"[,.;:()\[\]|]|\bi want to\b|\bi want\b|\bso that\b|\bi can\b")


def _runs(words: list[str]) -> set[tuple[str, ...]]:
    runs = {tuple(words[i : i + 4]) for i in range(len(words) - 3)}
    return {run for run in runs if any(w not in SCAFFOLD for w in run)}


def _grams(text: str) -> set[tuple[str, ...]]:
    """Four-word runs of a rendered prompt, except runs made only of stock scaffold
    words."""
    return _runs(_words(text))


def _fixture_grams(text: str) -> set[tuple[str, ...]]:
    """Four-word runs of a fixture, taken within clauses: story scaffolding ("As a
    clerk, I want to ... so that I can ...") would otherwise make every story
    share runs with every rubric example, and says nothing about copying."""
    grams: set[tuple[str, ...]] = set()
    for clause in _CLAUSE_BREAK.split(text.lower()):
        grams |= _runs(_words(clause))
    return grams


def _example_pieces(examples: list[str]) -> list[str]:
    pieces: list[str] = []
    for example in examples:
        pieces.extend(p.strip() for p in re.split(r"Obligation:|Stories:|\|", example) if p.strip())
    return pieces


# --- DependencyCritic (a plain `Corpus`) -------------------------------------

DEP = DEPENDENCY_CRITIC


def _dep_quotes(split: str, polarities: tuple[str, ...] = ("clean", "seeded")) -> list[str]:
    return [
        q
        for polarity in polarities
        for path in DEP.files(polarity, split)
        for q in load_fixture(path)["dependencies"]
    ]


def _dep_stress() -> list[str]:
    return [q for path in DEP.stress_files() for q in load_fixture(path)["dependencies"]]


def _dep_examples() -> list[frozenset[str]]:
    return [_tokens(e) for c in DEP.rubric.checks for e in (*c.examples_bad, *c.examples_good)]


@pytest.mark.parametrize("which", [*SPLITS, "stress"])
def test_no_dependency_fixture_paraphrases_a_rubric_example(which: str) -> None:
    quotes = _dep_stress() if which == "stress" else _dep_quotes(which)
    assert quotes
    for quote in quotes:
        for example in _dep_examples():
            assert _jaccard(_tokens(quote), example) <= MAX_VS_RUBRIC_EXAMPLE, quote


def test_dependency_dev_and_held_out_are_not_rewrites_of_each_other() -> None:
    for dev in _dep_quotes("dev"):
        for held in _dep_quotes("held_out"):
            assert _jaccard(_tokens(dev), _tokens(held)) <= MAX_BETWEEN_SPLITS, (dev, held)


def test_dependency_stress_is_not_a_paraphrase_of_the_gated_splits() -> None:
    gated = [_tokens(q) for split in SPLITS for q in _dep_quotes(split)]
    for quote in _dep_stress():
        for tokens in gated:
            assert _jaccard(_tokens(quote), tokens) <= MAX_BETWEEN_SPLITS, quote


def test_no_gated_dependency_repeats_a_four_word_run_from_the_rendered_prompt() -> None:
    prompt = _grams(
        build_system_prompt(DEP.rubric, DependencyCritic.preamble, DependencyCritic.judge_preamble)
    )
    for split in SPLITS:
        for quote in _dep_quotes(split):
            assert not _fixture_grams(quote) & prompt, quote
    for quote in _dep_stress():
        assert not _fixture_grams(quote) & prompt, quote


def test_each_dependency_seeded_split_covers_every_defect_shape_and_both_injection_forms() -> None:
    for split in SPLITS:
        kinds = [load_fixture(p)["kind"] for p in DEP.files("seeded", split)]
        assert len(set(kinds)) == len(kinds) == 12, split
        assert sum("injection" in k for k in kinds) == 2, split


def test_dependency_clean_sets_carry_every_boundary_shape_in_both_splits() -> None:
    """Named owners (two forms), obligations PB4 double-tags as dependencies, and
    reliances already satisfied: if the clean set were only 'Owner: Name' lines a
    surface-style split would score well."""
    for split in SPLITS:
        names = {p.stem for p in DEP.files("clean", split)}
        assert len(names) == 4 and any("not_a_dependency" in n for n in names), split
        assert any("already_satisfied" in n for n in names), split
        assert sum("named" in n for n in names) == 2, split


def test_dependency_stress_carries_the_known_false_positive_class() -> None:
    by_name = {p.stem: load_fixture(p) for p in DEP.stress_files()}
    assert by_name["owner_in_next_sentence"]["expect_fired"] == ["unowned_dependency"]
    assert "NEXT sentence" in by_name["owner_in_next_sentence"]["why"]


# --- ConstraintCritic (documents) -----------------------------------------

TRACE = CONSTRAINT_CRITIC


def _doc_quotes(
    split: str, key: str, polarities: tuple[str, ...] = ("clean", "seeded")
) -> list[str]:
    return [
        q
        for polarity in polarities
        for path in TRACE.files(polarity, split)
        for q in load_fixture(path)[key]
    ]


def _all_gated_quotes() -> list[str]:
    return [
        q
        for split in SPLITS
        for polarity in ("clean", "seeded")
        for path in TRACE.files(polarity, split)
        for q in TRACE.quotes(path)
    ]


def _stress_quotes() -> list[str]:
    return [q for path in TRACE.stress_files() for q in TRACE.quotes(path)]


def test_rubric_globs_find_every_document() -> None:
    clean, defect = resolve_fixture_paths(TRACE.rubric, TRACE.rubric_path)
    assert clean == sorted(p for s in SPLITS for p in TRACE.files("clean", s))
    assert defect == sorted(p for s in SPLITS for p in TRACE.files("seeded", s))
    assert clean and defect


@pytest.mark.parametrize("split", SPLITS)
def test_every_split_has_twelve_seeded_and_twelve_clean_documents(split: str) -> None:
    assert len(TRACE.files("seeded", split)) == 12
    assert len(TRACE.files("clean", split)) == 12


@pytest.mark.parametrize("split", SPLITS)
def test_a_seeded_document_names_the_check_and_marks_real_untraced_constraints(split: str) -> None:
    for path in TRACE.files("seeded", split):
        data = load_fixture(path)
        assert data["check"] == "untraced_obligation", path.name
        assert data["expect_untraced"], path.name
        assert set(data["expect_untraced"]) <= set(data["constraints"]), path.name
    for path in TRACE.files("clean", split):
        assert load_fixture(path)["expect_untraced"] == [], path.name


@pytest.mark.parametrize("split", SPLITS)
def test_seeded_documents_cover_every_decoy_shape_and_mix_traced_with_untraced(split: str) -> None:
    kinds = [load_fixture(p)["kind"] for p in TRACE.files("seeded", split)]
    assert len(set(kinds)) == len(kinds)
    assert {
        "same_area_decoys",
        "same_noun_different_act",
        "self_declared_trace",
        "story_claims_all",
        "injection_in_story",
        "injection_in_constraint",
    } <= set(kinds)
    mixed = [
        p
        for p in TRACE.files("seeded", split)
        if len(parse_trace_doc(p).expect_untraced) < len(parse_trace_doc(p).constraints)
    ]
    assert len(mixed) >= 6, split  # a document where a false block AND a false trace are possible


@pytest.mark.parametrize("split", SPLITS)
def test_clean_documents_carry_the_boundary_shapes(split: str) -> None:
    kinds = {p.stem.split("_", 2)[2] for p in TRACE.files("clean", split)}
    assert {
        "paraphrase_no_overlap",
        "one_story_two_constraints",
        "last_of_eight",
        "inline_acceptance_criteria",
        "inverse_injection_in_decoy",
        "three_constraints_three_stories",
    } <= kinds


def test_every_quote_resolves_round_trips_and_constraints_and_stories_never_overlap() -> None:
    for split in SPLITS:
        for polarity in ("clean", "seeded"):
            for path in TRACE.files(polarity, split):
                source = fixture_source(path)
                doc = parse_trace_doc(path)
                spans = [c.evidence for c in [*doc.constraints, *doc.stories]]
                for ev in spans:
                    assert source.text[ev.start : ev.end] == ev.text
                ordered = sorted(spans, key=lambda e: e.start)
                assert all(a.end <= b.start for a, b in pairwise(ordered)), path.name


def test_every_constraint_names_an_authority_as_pb4s_constraint_pass_requires() -> None:
    for quote in [*_doc_quotes("dev", "constraints"), *_doc_quotes("held_out", "constraints")]:
        assert AUTHORITY.search(quote), quote


@pytest.mark.parametrize("which", [*SPLITS, "stress"])
def test_no_document_text_paraphrases_a_rubric_example(which: str) -> None:
    pieces = [
        _tokens(p)
        for c in TRACE.rubric.checks
        for p in _example_pieces([*c.examples_bad, *c.examples_good])
    ]
    quotes = (
        _stress_quotes()
        if which == "stress"
        else [
            q
            for pol in ("clean", "seeded")
            for path in TRACE.files(pol, which)
            for q in TRACE.quotes(path)
        ]
    )
    assert quotes and pieces
    for quote in quotes:
        for piece in pieces:
            assert _jaccard(_tokens(quote), piece) <= MAX_VS_RUBRIC_EXAMPLE, (quote, piece)


@pytest.mark.parametrize("key", ["constraints", "stories"])
def test_dev_and_held_out_share_no_candidate_and_are_not_rewrites(key: str) -> None:
    dev, held = _doc_quotes("dev", key), _doc_quotes("held_out", key)
    assert set(dev).isdisjoint(held)
    for d in dev:
        for h in held:
            assert _jaccard(_tokens(d), _tokens(h)) <= MAX_BETWEEN_SPLITS, (d, h)


def test_stress_documents_are_not_paraphrases_of_the_gated_splits() -> None:
    gated = [_tokens(q) for q in _all_gated_quotes()]
    for quote in _stress_quotes():
        assert quote not in set(_all_gated_quotes())
        for tokens in gated:
            assert _jaccard(_tokens(quote), tokens) <= MAX_BETWEEN_SPLITS, quote


def test_no_gated_quote_repeats_a_four_word_run_from_the_rendered_prompt() -> None:
    prompt = _grams(
        build_trace_prompt(TRACE.rubric, ConstraintCritic.preamble, ConstraintCritic.judge_preamble)
    )
    for quote in [*_all_gated_quotes(), *_stress_quotes()]:
        assert not _fixture_grams(quote) & prompt, quote


def test_stress_documents_are_outside_the_s2_globs_and_well_formed() -> None:
    clean, defect = resolve_fixture_paths(TRACE.rubric, TRACE.rubric_path)
    stress = TRACE.stress_files()
    assert len(stress) >= 9
    assert not set(stress) & set(clean + defect)
    for path in stress:
        data = load_fixture(path)
        assert data["why"], path.name
        doc = parse_trace_doc(path)
        assert doc.expect_untraced.isdisjoint(doc.allow_untraced), path.name
        assert doc.constraints, path.name


def test_stress_carries_batching_chunking_and_the_no_stories_case() -> None:
    by_name = {p.stem: parse_trace_doc(p) for p in TRACE.stress_files()}
    assert len(by_name["large_batch"].constraints) == 8
    assert len(by_name["long_story_list"].stories) == 31  # one more than the default chunk (30)
    assert by_name["zero_stories"].stories == []
    assert by_name["zero_stories"].expect_untraced == {
        c.id for c in by_name["zero_stories"].constraints
    }


def test_the_guards_actually_catch_a_paraphrase() -> None:
    """Non-vacuity: a one-clause rewrite of a rubric example trips the limit."""
    original = "Invoices must be retained for seven years under the Finance Act."
    rewrite = "Invoices must be retained for eight years under the Finance Act."
    assert _jaccard(_tokens(rewrite), _tokens(original)) > MAX_VS_RUBRIC_EXAMPLE
    prompt = _grams("As a clerk I want to email a contract so that the supplier has a copy")
    assert _fixture_grams("As a user, I want to email a contract so that the supplier gets it")
    assert not _fixture_grams("As a user, I want to search notes so that I can find old ones")
    assert _fixture_grams("They email a contract so that the supplier has a copy") & prompt


def test_the_generator_reproduces_the_committed_corpus_exactly(tmp_path: Path) -> None:
    """The fixtures are generated data: a hand edit to a JSON file, or a generator edit
    with no regeneration, is a failing test rather than silent drift."""
    path = Path(__file__).parent.parent / "fixtures" / "critics" / "generate_pb7.py"
    spec = importlib.util.spec_from_file_location("generate_pb7", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main(tmp_path)
    for critic in ("constraint_critic", "dependency_critic"):
        committed = TRACE.rubric_path.parents[1] / critic
        for sub in ("fixtures", "stress"):
            regenerated = {
                p.relative_to(tmp_path / critic / sub): p
                for p in (tmp_path / critic / sub).rglob("*.json")
            }
            existing = {
                p.relative_to(committed / sub): p for p in (committed / sub).rglob("*.json")
            }
            assert regenerated.keys() == existing.keys(), (critic, sub)
            for rel, file in regenerated.items():
                assert file.read_bytes() == existing[rel].read_bytes(), (critic, sub, rel)


def test_held_out_seeds_include_obligation_grammar_that_needs_an_unowned_outside_party() -> None:
    """Pre-recording review B1: if every clean statement used 'must' and no seeded one
    did, 'must means met' would have scored 100% and the carve-out would be untested."""
    must = re.compile(r"\b(must|has to|have to|required to|needs to be)\b", re.IGNORECASE)
    for split in SPLITS:
        seeded = _dep_quotes(split, ("seeded",))
        assert sum(bool(must.search(q)) for q in seeded) >= 3, split
        clean = _dep_quotes(split, ("clean",))
        assert sum(bool(must.search(q)) for q in clean) >= 3, split


def test_the_untraced_constraint_is_not_always_first_in_a_seeded_document() -> None:
    """Review: it was first in 11 of 12 seeded slots, a positional tell."""
    for split in SPLITS:
        firsts = 0
        mixed = 0
        for path in TRACE.files("seeded", split):
            doc = parse_trace_doc(path)
            if len(doc.constraints) < 2 or len(doc.expect_untraced) == len(doc.constraints):
                continue
            mixed += 1
            ordered = sorted(doc.constraints, key=lambda c: c.evidence.start)
            firsts += ordered[0].id in doc.expect_untraced
        assert mixed >= 6 and firsts <= mixed - 2, (split, firsts, mixed)
