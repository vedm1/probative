"""Replays the committed PB7 recordings (tests/fixtures/critics/recordings/
{constraint_critic,dependency_critic}/) through the real `LiteLLMProvider` parse
path and pins what they scored.

No key, no network: the recordings are the reference model's answers, captured by
`test_pb7_live_record.py`. These tests do not measure the model; they hold the
critics, prompts, rubrics and corpora to the numbers the model earned when
recorded, so a change to any of them is a visible diff instead of silent drift.
Editing a prompt, rubric or fixture breaks the recording key on purpose; re-record.

The corpora are synthetic, single-author and reskinned between splits (OI21): read
the Implementation notes before quoting any number from here."""

from __future__ import annotations

import json
from typing import Any

import pytest

from probative.config import REFERENCE_MODEL
from probative.core.critic import Severity
from probative.critics import aggregate, assert_rubric_fixtures
from probative.critics.constraint_critic import ConstraintCritic
from probative.critics.dependency_critic import DependencyCritic
from probative.llm import FakeProvider, LiteLLMProvider
from tests.critics._candidates import fixture_source, load_fixture
from tests.critics._corpus import DEPENDENCY_CRITIC, SPLITS
from tests.critics._measure import measure, measure_mixed, measure_stress
from tests.critics._replay import recording_dir, replay_all_splits
from tests.critics._trace_corpus import CONSTRAINT_CRITIC, parse_trace_doc
from tests.critics._trace_measure import measure_trace, measure_trace_stress

ALL = (*SPLITS, "stress")
HINT = (
    "Re-record with `ANTHROPIC_API_KEY=... PB7C_SPLIT=<dev|held_out|stress> uv run pytest -m live "
    "tests/critics/test_pb7_live_record.py -k constraint -s` (ConstraintCritic) or PB7D_SPLIT "
    "with `-k dependency` (DependencyCritic). A prompt, rubric or fixture edit after held-out "
    "results exist demotes held_out to dev: write fresh held-out fixtures first."
)
DEP = DEPENDENCY_CRITIC
TRACE = CONSTRAINT_CRITIC


def _dep() -> DependencyCritic:
    provider = LiteLLMProvider(completion_fn=replay_all_splits(DEP.name, ALL, HINT))
    return DependencyCritic.from_builtin_rubric(provider, model=REFERENCE_MODEL)


def _con() -> ConstraintCritic:
    provider = LiteLLMProvider(completion_fn=replay_all_splits(TRACE.name, ALL, HINT))
    return ConstraintCritic.from_builtin_rubric(provider, model=REFERENCE_MODEL)


def _recorded(name: str, split: str) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(
        (recording_dir(name, split) / "results.json").read_text(encoding="utf-8")
    )
    return raw


# --- every recording ----------------------------------------------------------


@pytest.mark.parametrize("name", [DEP.name, TRACE.name])
@pytest.mark.parametrize("split", ALL)
def test_every_recorded_response_names_the_pinned_reference_model(name: str, split: str) -> None:
    """OI2: checked against what the API itself reported in each recorded response."""
    reference = REFERENCE_MODEL.split("/", 1)[1]
    recordings = [p for p in recording_dir(name, split).glob("*.json") if p.name != "results.json"]
    assert recordings
    for path in recordings:
        assert json.loads(path.read_text(encoding="utf-8"))["model"].startswith(reference)
    assert _recorded(name, split)["model"] == REFERENCE_MODEL


# --- DependencyCritic -----------------------------------------------------------


@pytest.mark.parametrize("split", SPLITS)
def test_dependency_replayed_measurement_equals_the_recorded_one(split: str) -> None:
    replayed = measure(DEP, split, _dep(), detail=True)
    recorded = {k: v for k, v in _recorded(DEP.name, split).items() if k != "model"}
    assert replayed == recorded


@pytest.mark.parametrize("split", SPLITS)
def test_dependency_s2_contract_holds_and_the_exact_counts_are_pinned(split: str) -> None:
    """S2: raise nothing on every clean fixture; catch every seeded defect. Counts are
    the ones recorded (n = 12 seeded and 12 clean statements per split)."""
    critic = _dep()
    for path in DEP.files("clean", split):
        assert critic.check(DEP.parse(path)) == [], path.name
    for path in DEP.files("seeded", split):
        fired = {f.check_id for f in critic.check(DEP.parse(path))}
        assert fired == {"unowned_dependency"}, path.name
    recorded = _recorded(DEP.name, split)
    assert recorded["seeded"]["n"] == recorded["seeded"]["caught"] == 12
    assert recorded["seeded"]["caught_intended"] == 12
    assert (recorded["clean"]["candidates"], recorded["clean"]["flagged_candidates"]) == (12, 0)


@pytest.mark.parametrize("split", SPLITS)
def test_dependency_findings_are_block_and_evidenced_by_real_source_text(split: str) -> None:
    """I1, against a real model's output; severity is the rubric's, not the model's."""
    critic = _dep()
    for path in DEP.files("seeded", split):
        source = fixture_source(path)
        candidates = {c.id: c for c in DEP.parse(path)}  # type: ignore[attr-defined]
        for finding in critic.check(list(candidates.values())):
            ev = finding.evidence
            assert ev is not None and finding.target_id in candidates
            assert source.text[ev.start : ev.end] == ev.text
            cand_ev = candidates[finding.target_id].evidence
            assert cand_ev.start <= ev.start < ev.end <= cand_ev.end
            assert (finding.severity, finding.invariant) == (Severity.BLOCK, None)


@pytest.mark.parametrize("split", SPLITS)
def test_dependency_the_model_never_produced_an_unusable_judgement(split: str) -> None:
    stats = _recorded(DEP.name, split)["judge_stats"]
    assert (stats["unresolved_quotes"], stats["unknown_ids"], stats["missing"]) == (0, 0, 0)
    for row in _recorded(DEP.name, split)["seeded"]["files"]:
        assert row["cannot_tell"] == 0, row["file"]  # the silent-pass hazard (OI21)


@pytest.mark.parametrize("split", SPLITS)
def test_dependency_injected_instructions_did_not_steer_the_reference_model(split: str) -> None:
    """Measured behaviour for this model at this prompt, not a structural guarantee."""
    critic = _dep()
    injected = [p for p in DEP.files("seeded", split) if "injection" in load_fixture(p)["kind"]]
    assert len(injected) == 2
    for path in injected:
        assert critic.check(DEP.parse(path)), path.name


@pytest.mark.parametrize("split", SPLITS)
def test_dependency_obligation_grammar_needing_an_outside_party_is_still_flagged(
    split: str,
) -> None:
    """Pre-recording review B1: the carve-out ('a rule the team itself must meet') must not
    swallow 'must be approved by <outside party>'; and plain obligations stay met."""
    critic = _dep()
    seeded_must = [
        p
        for p in DEP.files("seeded", split)
        if " must " in load_fixture(p)["dependencies"][0]
        or " has to " in load_fixture(p)["dependencies"][0]
    ]
    assert len(seeded_must) >= 3
    for path in seeded_must:
        assert critic.check(DEP.parse(path)), path.name
    plain = next(p for p in DEP.files("clean", split) if "not_a_dependency" in p.stem)
    assert critic.check(DEP.parse(plain)) == []


def test_dependency_assert_rubric_fixtures_passes_over_the_whole_corpus() -> None:
    assert_rubric_fixtures(_dep(), DEP.rubric_path, DEP.parse)


def test_dependency_replayed_stress_and_mixed_batch_equal_the_recorded_ones() -> None:
    recorded = _recorded(DEP.name, "stress")
    assert measure_stress(DEP, _dep()) == recorded["stress"]
    assert measure_mixed(DEP, _dep()) == recorded["mixed"]
    mixed = recorded["mixed"]
    assert (mixed["seeded"]["n"], mixed["seeded"]["caught"]) == (24, 24)
    assert (mixed["clean"]["candidates"], mixed["clean"]["flagged_candidates"]) == (24, 0)


PINNED_DEP_STRESS: dict[str, list[str]] = {
    "bare_noun_phrase.json": ["unowned_dependency"],
    "counterparty_person_certifies.json": [],
    "doc_voice_injection.json": ["unowned_dependency"],
    "first_name_only.json": [],
    "heading_only.json": [],
    "initials_only.json": [],
    "leads_the_building_team.json": ["unowned_dependency"],
    "name_without_responsibility.json": ["unowned_dependency"],
    "obligation_with_outside_party.json": [],
    "owner_in_next_sentence.json": ["unowned_dependency"],
    "owner_in_table_column.json": ["unowned_dependency"],
    "resolved_in_the_statement.json": [],
    "two_named_owners.json": [],
    "we_will_own_it.json": ["unowned_dependency"],
}


def test_dependency_stress_outcomes_are_pinned_per_case() -> None:
    """Reported, never gating, never tuned on. 'As labelled' is lenient by design: the
    cases labelled 'defensible either way' tolerate a flag without requiring one, so the
    strict count (fired == expected) is lower. The two false positives the module
    docstring predicts (owner in the next sentence, owner in another table cell) fire."""
    stress = _recorded(DEP.name, "stress")["stress"]
    assert stress["as_expected"] == stress["n"] == len(DEP.stress_files()) == 14
    assert {r["file"]: r["fired"] for r in stress["files"]} == PINNED_DEP_STRESS
    strict = sum(r["fired"] == r["expect_fired"] for r in stress["files"])
    assert strict == 13  # leads_the_building_team fired where only 'either way' was labelled
    assert stress["judge_stats"]["cannot_tell"] == 1  # heading_only


# --- ConstraintCritic -----------------------------------------------------------


@pytest.mark.parametrize("split", SPLITS)
def test_constraint_replayed_measurement_equals_the_recorded_one(split: str) -> None:
    replayed = measure_trace(TRACE, split, _con())
    recorded = {k: v for k, v in _recorded(TRACE.name, split).items() if k != "model"}
    assert replayed == recorded


@pytest.mark.parametrize("split", SPLITS)
def test_constraint_flags_exactly_the_untraced_constraints_and_the_counts_are_pinned(
    split: str,
) -> None:
    """S2 and more: in a seeded document the flagged set equals `expect_untraced` (no false
    block on a traced constraint, no false trace on an untraced one); in a clean document
    nothing is flagged and every constraint carries a verified link."""
    critic = _con()
    for path in TRACE.files("seeded", split):
        doc = parse_trace_doc(path)
        result = critic.check_with_traces(doc.candidates)
        assert {f.target_id for f in result.findings} == doc.expect_untraced, path.name
        traced = {c.id for c in doc.constraints} - doc.expect_untraced
        assert {k.constraint_id for k in result.links} == traced, path.name
    for path in TRACE.files("clean", split):
        doc = parse_trace_doc(path)
        result = critic.check_with_traces(doc.candidates)
        assert result.findings == [], path.name
        assert {k.constraint_id for k in result.links} == {c.id for c in doc.constraints}
    recorded = _recorded(TRACE.name, split)
    seeded, clean = recorded["seeded"], recorded["clean"]
    assert (seeded["documents"], seeded["documents_caught_all"]) == (12, 12)
    assert (seeded["untraced_constraints"], seeded["caught"]) == (14, 14)
    assert (seeded["traced_constraints"], seeded["flagged_traced"]) == (8, 0)
    assert (clean["documents"], clean["constraints"], clean["flagged_constraints"]) == (12, 16, 0)


@pytest.mark.parametrize("split", SPLITS)
def test_constraint_findings_and_links_are_evidenced_by_real_source_text(split: str) -> None:
    """I1, against a real model's output: a finding's evidence is the constraint's own
    span; a link's evidence is a phrase sliced from a story of the SAME document, inside
    that story."""
    critic = _con()
    for polarity in ("seeded", "clean"):
        for path in TRACE.files(polarity, split):
            source = fixture_source(path)
            doc = parse_trace_doc(path)
            stories = {s.id: s for s in doc.stories}
            constraints = {c.id: c for c in doc.constraints}
            result = critic.check_with_traces(doc.candidates)
            for finding in result.findings:
                ev = finding.evidence
                assert ev is not None and finding.target_id in constraints
                assert ev == constraints[finding.target_id].evidence
                assert source.text[ev.start : ev.end] == ev.text
                assert (finding.severity, finding.invariant) == (Severity.BLOCK, "I8")
            for link in result.links:
                story_ev = stories[link.story_id].evidence
                assert link.constraint_id in constraints
                assert source.text[link.evidence.start : link.evidence.end] == link.evidence.text
                assert story_ev.start <= link.evidence.start < link.evidence.end <= story_ev.end


@pytest.mark.parametrize("split", SPLITS)
def test_constraint_the_model_never_produced_an_unusable_judgement(split: str) -> None:
    stats = _recorded(TRACE.name, split)["judge_stats"]
    assert (stats["missing"], stats["unknown_ids"], stats["unverified_links"]) == (0, 0, 0)
    assert stats["no_story_docs"] == 0


@pytest.mark.parametrize("split", SPLITS)
def test_constraint_injected_instructions_did_not_steer_the_reference_model(split: str) -> None:
    """Measured behaviour for this model at this prompt, not a structural guarantee: the
    seeded injections (in a story, in a constraint) still end in the right block, and the
    clean document whose decoy story tries to force a false block raises nothing."""
    critic = _con()
    injected = [p for p in TRACE.files("seeded", split) if "injection" in load_fixture(p)["kind"]]
    assert len(injected) == 2
    for path in injected:
        doc = parse_trace_doc(path)
        flagged = {f.target_id for f in critic.check(doc.candidates)}
        assert flagged == doc.expect_untraced, path.name
    (inverse,) = [p for p in TRACE.files("clean", split) if "inverse_injection" in p.stem]
    assert critic.check(parse_trace_doc(inverse).candidates) == []


@pytest.mark.parametrize("split", SPLITS)
def test_constraint_a_block_zeroes_the_dimension(split: str) -> None:
    critic = _con()
    path = TRACE.files("seeded", split)[0]
    findings = critic.check(parse_trace_doc(path).candidates)
    (dimension,) = aggregate([TRACE.rubric], findings)
    assert dimension.blocked and dimension.score == 0.0


def test_constraint_assert_rubric_fixtures_passes_over_the_whole_corpus() -> None:
    """PB3's S2 gate, verbatim, over dev and held-out together."""
    assert_rubric_fixtures(_con(), TRACE.rubric_path, TRACE.parse)


def test_constraint_replayed_stress_equals_the_recorded_one() -> None:
    recorded = _recorded(TRACE.name, "stress")
    assert measure_trace_stress(TRACE, _con()) == recorded["stress"]


PINNED_TRACE_STRESS: dict[str, int] = {  # file -> constraints flagged
    "acceptance_criterion_trace.json": 0,
    "extraction_false_positive_shape.json": 1,
    "force_false_block_injection.json": 0,
    "large_batch.json": 5,
    "long_story_list.json": 1,
    "partial_coverage.json": 0,
    "report_vs_file_delivery.json": 1,
    "story_traces_the_other_obligation.json": 1,
    "vague_obligation.json": 1,
    "zero_stories.json": 2,
}


def test_constraint_stress_outcomes_are_pinned_per_case() -> None:
    """Reported, never gating, never tuned on. 'As labelled' is lenient by design: the two
    cases labelled 'defensible either way' tolerate a flag without requiring one, so the
    strict count (flagged == expected) is lower: `report_vs_file_delivery` was flagged
    where only 'either way' was labelled."""
    stress = _recorded(TRACE.name, "stress")["stress"]
    assert stress["as_expected"] == stress["n"] == len(TRACE.stress_files()) == 10
    assert {r["file"]: len(r["flagged"]) for r in stress["files"]} == PINNED_TRACE_STRESS
    strict = sum(r["flagged"] == r["expect_untraced"] for r in stress["files"])
    assert strict == 9
    stats = stress["judge_stats"]
    assert (stats["missing"], stats["unknown_ids"], stats["unverified_links"]) == (0, 0, 0)
    assert stats["no_story_docs"] == 1


def test_constraint_the_8_constraint_document_was_batched_and_the_31_story_one_was_chunked() -> (
    None
):
    """Batching (5 + 3) and chunking (30 + 1) were exercised live, not only in unit tests:
    the recorded call count for the stress run is what the structure predicts."""
    large = parse_trace_doc(next(p for p in TRACE.stress_files() if p.stem == "large_batch"))
    long_ = parse_trace_doc(next(p for p in TRACE.stress_files() if p.stem == "long_story_list"))
    assert len(large.constraints) == 8 and len(long_.stories) == 31
    # 10 documents; zero_stories makes no call, so 9 make one, plus one more for
    # large_batch's second batch (5 + 3) and one for long_story_list's second chunk.
    calls = _recorded(TRACE.name, "stress")["stress"]["judge_stats"]["calls"]
    assert calls == 11


def test_constraint_zero_stories_makes_no_model_call() -> None:
    doc = parse_trace_doc(next(p for p in TRACE.stress_files() if p.stem == "zero_stories"))
    critic = ConstraintCritic.from_builtin_rubric(FakeProvider([]), model="m")
    assert {f.target_id for f in critic.check(doc.candidates)} == doc.expect_untraced
