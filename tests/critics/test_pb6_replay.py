"""Replays the committed PB6 recordings (tests/fixtures/critics/recordings/
{evidence_auditor,segment_skeptic}/) through the real `LiteLLMProvider` parse
path and pins what they scored, for both PB6 critics (p1 EvidenceAuditor, p2
SegmentSkeptic).

No key, no network: the recordings are the reference model's answers, captured
once by `test_pb6_live_record.py` / `test_pb6p2_live_record.py`. These tests do
not measure the model; they hold the critics, prompts, rubrics and corpora to the
numbers the model earned when recorded, so a change to any of them is a visible
diff instead of silent drift. Editing a prompt, rubric or fixture breaks the
recording key on purpose; re-record.

The corpora are synthetic and single-author (OI21): read the Implementation notes
before quoting any number from here."""

from __future__ import annotations

import json
from typing import Any

import pytest

from probative.config import REFERENCE_MODEL
from probative.core.critic import Severity
from probative.critics import assert_rubric_fixtures
from probative.critics.evidence_auditor import EvidenceAuditor
from probative.critics.llm_judge import LLMCritic
from probative.critics.segment_skeptic import SegmentSkeptic
from probative.llm import LiteLLMProvider
from tests.critics._candidates import fixture_source, load_fixture
from tests.critics._corpus import EVIDENCE_AUDITOR, SEGMENT_SKEPTIC, SPLITS, Corpus
from tests.critics._measure import measure, measure_mixed, measure_stress
from tests.critics._replay import recording_dir, replay_all_splits

ALL = (*SPLITS, "stress")
HINT = (
    "Re-record with `ANTHROPIC_API_KEY=... PB6_SPLIT=<dev|held_out|stress> uv run pytest -m live "
    "tests/critics/test_pb6_live_record.py -s` (EvidenceAuditor) or the PB6P2_SPLIT equivalent "
    "in test_pb6p2_live_record.py (SegmentSkeptic)."
)
CRITICS: list[tuple[Corpus, type[LLMCritic]]] = [
    (EVIDENCE_AUDITOR, EvidenceAuditor),
    (SEGMENT_SKEPTIC, SegmentSkeptic),
]
CASES = [(c, k, s) for c, k in CRITICS for s in SPLITS]
IDS = [f"{c.name}-{s}" for c, _, s in CASES]
CRITIC_IDS = [c.name for c, _ in CRITICS]


def _critic(corpus: Corpus, critic_cls: type[LLMCritic]) -> LLMCritic:
    provider = LiteLLMProvider(completion_fn=replay_all_splits(corpus.name, ALL, HINT))
    return critic_cls.from_builtin_rubric(provider, model=REFERENCE_MODEL)  # type: ignore[attr-defined, no-any-return]


def _recorded(corpus: Corpus, split: str) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(
        (recording_dir(corpus.name, split) / "results.json").read_text(encoding="utf-8")
    )
    return raw


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_every_recorded_response_names_the_pinned_reference_model(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    """OI2: checked against what the API itself reported in each recorded response."""
    reference = REFERENCE_MODEL.split("/", 1)[1]
    recordings = [
        p for p in recording_dir(corpus.name, split).glob("*.json") if p.name != "results.json"
    ]
    assert recordings
    for path in recordings:
        assert json.loads(path.read_text(encoding="utf-8"))["model"].startswith(reference)


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_replayed_measurement_equals_the_recorded_one(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    replayed = measure(corpus, split, _critic(corpus, critic_cls), detail=True)
    recorded = {k: v for k, v in _recorded(corpus, split).items() if k != "model"}
    assert replayed == recorded


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_s2_contract_holds_on_the_recorded_split(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    """S2: raise nothing on every clean fixture; catch every seeded defect."""
    critic = _critic(corpus, critic_cls)
    for path in corpus.files("clean", split):
        assert critic.check(corpus.parse(path)) == [], path.name
    for path in corpus.files("seeded", split):
        assert critic.check(corpus.parse(path)), path.name


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_every_defect_trips_the_check_it_was_seeded_for_and_any_extra_is_pinned(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    """The intended check must fire. Another check firing on the same defect is not a
    false positive, but it is visible: the exact set of such extras is pinned, so a new
    one is a deliberate edit rather than drift."""
    critic = _critic(corpus, critic_cls)
    extras: dict[str, list[str]] = {}
    for path in corpus.files("seeded", split):
        intended = load_fixture(path)["check"]
        fired = {f.check_id for f in critic.check(corpus.parse(path))}
        assert intended in fired, (path.name, fired)
        if fired - {intended}:
            extras[path.name] = sorted(fired - {intended})
    assert extras == PINNED_EXTRAS.get((corpus.name, split), {})


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_every_finding_is_evidenced_by_text_that_is_really_in_the_source(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    """I1, against a real model's output."""
    critic = _critic(corpus, critic_cls)
    for path in corpus.files("seeded", split):
        source = fixture_source(path)
        candidates = {c.id: c for c in corpus.parse(path)}  # type: ignore[attr-defined]
        for finding in critic.check(list(candidates.values())):
            ev = finding.evidence
            assert ev is not None and finding.target_id in candidates
            assert source.text[ev.start : ev.end] == ev.text
            cand_ev = candidates[finding.target_id].evidence
            assert cand_ev.start <= ev.start < ev.end <= cand_ev.end


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_the_model_never_produced_an_unusable_judgement(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    stats = _recorded(corpus, split)["judge_stats"]
    assert (stats["unresolved_quotes"], stats["unknown_ids"], stats["missing"]) == (0, 0, 0)


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_no_seeded_defect_was_passed_by_a_cannot_tell(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    """The silent-pass hazard of a blocking critic (PB5 accepted gap, OI21): a seeded defect judged
    cannot_tell is not caught for the right reason."""
    for row in _recorded(corpus, split)["seeded"]["files"]:
        assert row["cannot_tell"] == 0, row["file"]


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_injected_instructions_did_not_steer_the_reference_model(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    """Measured behaviour for this model at this prompt, not a structural guarantee."""
    critic = _critic(corpus, critic_cls)
    injected = [p for p in corpus.files("seeded", split) if "injection" in load_fixture(p)["kind"]]
    assert injected, split
    for path in injected:
        intended = load_fixture(path)["check"]
        assert intended in {f.check_id for f in critic.check(corpus.parse(path))}, path.name


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_findings_carry_the_severity_of_their_own_check(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    rubric = corpus.rubric
    effective = {c.id: c.severity or rubric.severity for c in rubric.checks}
    critic = _critic(corpus, critic_cls)
    for path in corpus.files("seeded", split):
        for finding in critic.check(corpus.parse(path)):
            assert finding.severity == effective[finding.check_id], path.name
    assert Severity.BLOCK in effective.values()


@pytest.mark.parametrize(("corpus", "critic_cls"), CRITICS, ids=CRITIC_IDS)
def test_assert_rubric_fixtures_passes_over_the_whole_corpus(
    corpus: Corpus, critic_cls: type[LLMCritic]
) -> None:
    """PB3's S2 gate, verbatim, over dev and held-out together."""
    assert_rubric_fixtures(_critic(corpus, critic_cls), corpus.rubric_path, corpus.parse)


@pytest.mark.parametrize(("corpus", "critic_cls"), CRITICS, ids=CRITIC_IDS)
def test_replayed_stress_and_mixed_batch_equal_the_recorded_ones(
    corpus: Corpus, critic_cls: type[LLMCritic]
) -> None:
    recorded = _recorded(corpus, "stress")
    assert measure_stress(corpus, _critic(corpus, critic_cls)) == recorded["stress"]
    assert measure_mixed(corpus, _critic(corpus, critic_cls)) == recorded["mixed"]


@pytest.mark.parametrize(("corpus", "critic_cls"), CRITICS, ids=CRITIC_IDS)
def test_stress_outcomes_are_pinned_per_case(corpus: Corpus, critic_cls: type[LLMCritic]) -> None:
    """Which hard cases fired what. Reported, never gating, never tuned on: a change
    here is a deliberate edit to what the corpus says about the model's limits."""
    stress = _recorded(corpus, "stress")["stress"]
    assert stress["as_expected"] == stress["n"] == len(corpus.stress_files())
    assert {row["file"]: row["fired"] for row in stress["files"]} == PINNED_STRESS[corpus.name]


PINNED_STRESS: dict[str, dict[str, list[str]]] = {
    "evidence_auditor": {
        "adjacent_source.json": ["unsourced_statistic"],
        "city_to_country.json": ["basis_overreach"],
        "count_own_things.json": [],
        "doc_voice_injection.json": ["unsourced_statistic"],
        "form_minutes.json": ["unsourced_statistic"],
        "invite_expiry_rule.json": [],
        "opinion_unmarked.json": ["unsourced_assertion"],
        "our_analytics.json": [],
        "pdf_lost_marker.json": [],
        "roughly_half.json": ["unsourced_statistic"],
        "survey_of_nine.json": ["basis_overreach"],
        "survey_slightly_stretched.json": ["basis_overreach"],
        "truism.json": ["unsourced_assertion"],
        "weasel_hedge.json": [],
    },
    "segment_skeptic": {
        "all_adults.json": ["demographic_only", "whole_market"],
        "all_small_businesses.json": ["demographic_only"],
        "any_owner_with_a_condition.json": [],
        "bare_acronym.json": ["demographic_only"],
        "doc_voice_injection.json": ["demographic_only"],
        "firmographic_with_pain.json": [],
        "heading_label.json": [],
        "income_band_only.json": ["demographic_only"],
        "need_in_next_sentence.json": ["demographic_only"],
        "occupation_plus_vague_goal.json": [],
        "psychographic_adjectives.json": ["demographic_only"],
        "role_with_task.json": [],
        "size_with_behaviour.json": [],
        "two_sentence_definition.json": [],
        "uses_competitor_app.json": ["demographic_only"],
    },
}

# (critic, split) -> {seeded file: checks that fired besides the one it was seeded for}
PINNED_EXTRAS: dict[tuple[str, str], dict[str, list[str]]] = {
    ("evidence_auditor", "dev"): {"claim_01_figure_mid_sentence.json": ["unsourced_assertion"]},
    ("segment_skeptic", "held_out"): {
        "segment_10_consumers_at_large.json": ["demographic_only"],
        "segment_12_injection_format_instruction.json": ["demographic_only"],
    },
}
