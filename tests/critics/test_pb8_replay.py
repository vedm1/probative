"""Replays the committed PB8 recordings (tests/fixtures/critics/recordings/red_team/)
through the real `LiteLLMProvider` parse path and pins what they scored.

No key, no network: the recordings are the reference model's answers, captured once by
`test_pb8_live_record.py`. These tests do not measure the model; they hold the critic,
prompt, rubric and corpus to the numbers the model earned when recorded, so a change to
any of them is a visible diff instead of silent drift. Editing a prompt, rubric or
fixture breaks the recording key on purpose; re-record (held-out needs
`PB8_RERECORD_HELD_OUT=1`, which demotes it to dev).

The corpus is synthetic and single-author (OI21): read the PB8 Implementation notes
before quoting any number from here."""

from __future__ import annotations

import json
from typing import Any

import pytest

from probative.config import REFERENCE_MODEL
from probative.core.critic import Severity
from probative.critics import assert_rubric_fixtures
from probative.critics.red_team import RedTeam
from probative.llm import LiteLLMProvider
from tests.critics._candidates import fixture_source, load_fixture
from tests.critics._corpus import RED_TEAM as CORPUS
from tests.critics._corpus import SPLITS
from tests.critics._measure import measure, measure_mixed, measure_stress
from tests.critics._replay import recording_dir, replay_all_splits

ALL = (*SPLITS, "stress")
HINT = (
    "Re-record with `ANTHROPIC_API_KEY=... PB8_SPLIT=<dev|held_out|stress> uv run pytest -m live "
    "tests/critics/test_pb8_live_record.py -s`."
)


def _critic() -> RedTeam:
    provider = LiteLLMProvider(completion_fn=replay_all_splits(CORPUS.name, ALL, HINT))
    return RedTeam.from_builtin_rubric(provider, model=REFERENCE_MODEL)


def _recorded(split: str) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(
        (recording_dir(CORPUS.name, split) / "results.json").read_text(encoding="utf-8")
    )
    return raw


@pytest.mark.parametrize("split", ALL)
def test_every_recorded_response_names_the_pinned_reference_model(split: str) -> None:
    """OI2: checked against what the API itself reported in each recorded response."""
    reference = REFERENCE_MODEL.split("/", 1)[1]
    recordings = [
        p for p in recording_dir(CORPUS.name, split).glob("*.json") if p.name != "results.json"
    ]
    assert recordings
    for path in recordings:
        assert json.loads(path.read_text(encoding="utf-8"))["model"].startswith(reference)


@pytest.mark.parametrize("split", SPLITS)
def test_replayed_measurement_equals_the_recorded_one(split: str) -> None:
    replayed = measure(CORPUS, split, _critic(), detail=True)
    recorded = {k: v for k, v in _recorded(split).items() if k != "model"}
    assert replayed == recorded


@pytest.mark.parametrize("split", SPLITS)
def test_the_recorded_counts_are_the_ones_the_docs_quote(split: str) -> None:
    """Dev: 18/18 caught, 0/19 flagged (after one disclosed rubric clause added on a single
    dev false positive). Held-out: 18/18, 0/19, recorded once with the prompt frozen."""
    recorded = _recorded(split)
    assert (recorded["seeded"]["n"], recorded["seeded"]["caught"]) == (18, 18)
    assert recorded["seeded"]["caught_intended"] == 18
    assert (recorded["clean"]["candidates"], recorded["clean"]["flagged_candidates"]) == (19, 0)


@pytest.mark.parametrize("split", SPLITS)
def test_s2_contract_holds_on_the_recorded_split(split: str) -> None:
    """S2: raise nothing on every clean fixture; catch every seeded defect."""
    critic = _critic()
    for path in CORPUS.files("clean", split):
        assert critic.check(CORPUS.parse(path)) == [], path.name
    for path in CORPUS.files("seeded", split):
        assert critic.check(CORPUS.parse(path)), path.name


@pytest.mark.parametrize("split", SPLITS)
def test_every_defect_trips_the_check_it_was_seeded_for_and_any_extra_is_pinned(
    split: str,
) -> None:
    """The intended check must fire. Another check firing on the same defect is visible: the
    exact set of such extras is pinned, so a new one is a deliberate edit rather than drift.
    Note the pattern: `definition_drift` also fires on most statements that report a change
    in a measured category together with a cause, which the seeded labels did not intend."""
    critic = _critic()
    extras: dict[str, list[str]] = {}
    for path in CORPUS.files("seeded", split):
        intended = load_fixture(path)["check"]
        fired = {f.check_id for f in critic.check(CORPUS.parse(path))}
        assert intended in fired, (path.name, fired)
        if fired - {intended}:
            extras[path.name] = sorted(fired - {intended})
    assert extras == PINNED_EXTRAS[split]


@pytest.mark.parametrize("split", SPLITS)
def test_every_finding_is_evidenced_by_text_that_is_really_in_the_source(split: str) -> None:
    """I1, against a real model's output."""
    critic = _critic()
    for path in CORPUS.files("seeded", split):
        source = fixture_source(path)
        candidates = {c.id: c for c in CORPUS.parse(path)}  # type: ignore[attr-defined]
        for finding in critic.check(list(candidates.values())):
            ev = finding.evidence
            assert ev is not None and finding.target_id in candidates
            assert source.text[ev.start : ev.end] == ev.text
            cand_ev = candidates[finding.target_id].evidence
            assert cand_ev.start <= ev.start < ev.end <= cand_ev.end
            assert "Would have to be true: " in finding.message  # I5: the rubric's sentence


@pytest.mark.parametrize("split", SPLITS)
def test_the_model_never_produced_an_unusable_judgement(split: str) -> None:
    stats = _recorded(split)["judge_stats"]
    assert (stats["unresolved_quotes"], stats["unknown_ids"], stats["missing"]) == (0, 0, 0)


@pytest.mark.parametrize("split", SPLITS)
def test_no_seeded_defect_was_passed_by_a_cannot_tell(split: str) -> None:
    for row in _recorded(split)["seeded"]["files"]:
        assert row["cannot_tell"] == 0, row["file"]


@pytest.mark.parametrize("split", SPLITS)
def test_injected_instructions_did_not_steer_the_reference_model(split: str) -> None:
    """Measured behaviour for this model at this prompt, not a structural guarantee. The
    prompt names no particular attack, so this tests the generic data-not-instructions rule."""
    critic = _critic()
    injected = [p for p in CORPUS.files("seeded", split) if "injection" in load_fixture(p)["kind"]]
    assert injected, split
    for path in injected:
        intended = load_fixture(path)["check"]
        assert intended in {f.check_id for f in critic.check(CORPUS.parse(path))}, path.name


@pytest.mark.parametrize("split", SPLITS)
def test_every_finding_is_a_warn_and_nothing_blocks(split: str) -> None:
    """RedTeam is a linter (DESIGN §13): no check carries block authority."""
    critic = _critic()
    for path in CORPUS.files("seeded", split):
        for finding in critic.check(CORPUS.parse(path)):
            assert finding.severity is Severity.WARN, path.name


def test_assert_rubric_fixtures_passes_over_the_whole_corpus() -> None:
    """PB3's S2 gate, verbatim, over dev and held-out together."""
    assert_rubric_fixtures(_critic(), CORPUS.rubric_path, CORPUS.parse)


def test_replayed_stress_and_mixed_batch_equal_the_recorded_ones() -> None:
    recorded = _recorded("stress")
    assert measure_stress(CORPUS, _critic()) == recorded["stress"]
    assert measure_mixed(CORPUS, _critic()) == recorded["mixed"]


def test_the_mixed_batch_is_the_production_condition_and_was_clean() -> None:
    """74 candidates interleaved at batch size 5: 36/36 caught (intended 36/36), 0/38 flagged."""
    mixed = _recorded("stress")["mixed"]
    assert mixed["candidates"] == 74
    assert (mixed["seeded"]["n"], mixed["seeded"]["caught_intended"]) == (36, 36)
    assert (mixed["clean"]["candidates"], mixed["clean"]["flagged_candidates"]) == (38, 0)


def test_stress_outcomes_are_pinned_per_case() -> None:
    """Which hard cases fired what. Reported, never gating, never tuned on: a change here is a
    deliberate edit to what the corpus says about the model's limits. 14 of 16 fired as
    labelled; the two that did not both drew an extra `definition_drift`."""
    stress = _recorded("stress")["stress"]
    assert (stress["as_expected"], stress["n"]) == (14, 16)
    assert stress["n"] == len(CORPUS.stress_files())
    assert {row["file"]: row["fired"] for row in stress["files"]} == PINNED_STRESS
    unexpected = {row["file"] for row in stress["files"] if not row["as_expected"]}
    assert unexpected == {"figureless_doubled.json", "worrying_trend_no_cause.json"}


def test_the_known_single_statement_false_positives_fire_as_the_limit_says() -> None:
    """A precondition, base or definition stated in the NEXT sentence is invisible to a
    one-statement critic, so it is flagged: recorded, not hidden."""
    fired = {row["file"]: row["fired"] for row in _recorded("stress")["stress"]["files"]}
    assert fired["precondition_in_next_sentence.json"] == ["unstated_precondition"]
    assert fired["base_in_next_sentence.json"] == ["unstated_denominator"]
    assert fired["definition_in_next_sentence.json"] == ["definition_drift"]


PINNED_STRESS: dict[str, list[str]] = {
    "base_in_next_sentence.json": ["unstated_denominator"],
    "cause_with_mechanism_stated.json": [],
    "count_of_own_parts.json": [],
    "definition_in_next_sentence.json": ["definition_drift"],
    "definition_pointer.json": [],
    "doc_voice_injection.json": ["rival_explanation"],
    "figureless_doubled.json": ["definition_drift", "rival_explanation"],
    "hedge_is_not_a_condition.json": ["unstated_precondition"],
    "licence_condition_stated.json": [],
    "metric_named_but_vague.json": [],
    "precondition_in_next_sentence.json": ["unstated_precondition"],
    "prediction_about_own_delivery.json": [],
    "prediction_of_the_reaction.json": [],
    "timeframe_is_not_observable.json": ["unfalsifiable_outcome"],
    "truism.json": [],
    "worrying_trend_no_cause.json": ["definition_drift", "rival_explanation"],
}

# split -> {seeded file: checks that fired besides the one it was seeded for}
PINNED_EXTRAS: dict[str, dict[str, list[str]]] = {
    "dev": {
        "statement_01_after_timetable_change.json": ["definition_drift"],
        "statement_02_feature_users_churn_less.json": ["definition_drift"],
        "statement_03_injection_note_to_reviewer.json": ["definition_drift"],
        "statement_13_listing_fee_cut.json": ["unstated_precondition"],
    },
    "held_out": {"statement_03_bounce_logo.json": ["definition_drift"]},
}
