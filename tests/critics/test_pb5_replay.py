"""Replays the committed PB5 recordings (tests/fixtures/critics/recordings/)
through the real `LiteLLMProvider` parse path and pins what they scored.

No key, no network: the recordings are the reference model's answers,
captured once by `test_pb5_live_record.py`. These tests do not measure the
model — they hold the critics, prompts, rubrics and corpus to the numbers the
model earned when recorded, so a change to any of them is a visible diff
instead of a silent drift. Editing a prompt, rubric or fixture breaks the
recording key on purpose; re-record (see `_replay.RERECORD_HINT`).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from probative.config import REFERENCE_MODEL
from probative.core.critic import Severity
from probative.critics import assert_rubric_fixtures
from probative.critics.invest import INVESTCritic
from probative.critics.llm_judge import LLMCritic
from probative.critics.space_warden import SpaceWarden
from probative.llm import LiteLLMProvider
from tests.critics._candidates import fixture_source, load_fixture
from tests.critics._corpus import INVEST, SPACE_WARDEN, Corpus
from tests.critics._measure import measure
from tests.critics._replay import RERECORD_HINT, recording_dir, replay_all_splits

RECORDED_SPLITS = ("dev", "held_out")
CASES = [
    (corpus, critic_cls, split)
    for corpus, critic_cls in ((SPACE_WARDEN, SpaceWarden), (INVEST, INVESTCritic))
    for split in RECORDED_SPLITS
]
IDS = [f"{c.name}-{s}" for c, _, s in CASES]


def _critic(corpus: Corpus, critic_cls: type[LLMCritic]) -> LLMCritic:
    provider = LiteLLMProvider(completion_fn=replay_all_splits(corpus.name, RECORDED_SPLITS))
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
    """OI2: published numbers come from one pinned model. Checked against what
    the API itself reported in each recorded response, not a constant this repo
    wrote into `results.json` (which the recording key ignores)."""
    reference = REFERENCE_MODEL.split("/", 1)[1]  # "anthropic/claude-sonnet-5" -> "claude-sonnet-5"
    recordings = [
        p for p in recording_dir(corpus.name, split).glob("*.json") if p.name != "results.json"
    ]
    assert recordings
    for path in recordings:
        reported = json.loads(path.read_text(encoding="utf-8"))["model"]
        assert reported.startswith(reference), (path.name, reported)


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_replayed_measurement_equals_the_recorded_one(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    replayed = measure(corpus, split, _critic(corpus, critic_cls))
    recorded = {k: v for k, v in _recorded(corpus, split).items() if k != "model"}
    # `duplicates` was added to the stats after these were recorded; replaying the very same
    # replies shows there were none, which is the only claim made about it.
    assert replayed["judge_stats"].pop("duplicates") == 0
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
def test_every_defect_trips_the_check_it_was_seeded_for(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    critic = _critic(corpus, critic_cls)
    for path in corpus.files("seeded", split):
        intended = load_fixture(path)["check"]
        fired = {f.check_id for f in critic.check(corpus.parse(path))}
        assert intended in fired, (path.name, fired)


@pytest.mark.parametrize(("corpus", "critic_cls", "split"), CASES, ids=IDS)
def test_every_finding_is_evidenced_by_text_that_is_really_in_the_source(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    """I1, against a real model's output: a finding's evidence re-extracts to its
    recorded text and lies inside the candidate it is about."""
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
def test_the_model_never_produced_a_quote_the_candidate_does_not_contain(
    corpus: Corpus, critic_cls: type[LLMCritic], split: str
) -> None:
    stats = _recorded(corpus, split)["judge_stats"]
    assert (stats["unresolved_quotes"], stats["unknown_ids"], stats["missing"]) == (0, 0, 0)


@pytest.mark.parametrize("split", RECORDED_SPLITS)
def test_injected_instructions_did_not_steer_the_reference_model(split: str) -> None:
    """Measured behaviour for this model at this prompt, not a structural
    guarantee: a solution-shaped need that tells the critic to pass it is still
    flagged, and a clean need that tells it to flag is not."""
    critic = _critic(SPACE_WARDEN, SpaceWarden)
    for path in SPACE_WARDEN.files("seeded", split):
        if load_fixture(path)["defect"] == "injection":
            assert critic.check(SPACE_WARDEN.parse(path)), path.name
    for path in SPACE_WARDEN.files("clean", split):
        text = path.read_text(encoding="utf-8").lower()
        if "critic" in text or "instruction" in text:
            assert critic.check(SPACE_WARDEN.parse(path)) == [], path.name


def test_invest_findings_follow_the_rubric_severity_policy() -> None:
    critic = _critic(INVEST, INVESTCritic)
    for path in INVEST.files("seeded", "dev"):
        for finding in critic.check(INVEST.parse(path)):
            expected = Severity.BLOCK if finding.check_id == "testable" else Severity.WARN
            assert finding.severity == expected, (path.name, finding.check_id)


@pytest.mark.parametrize(
    ("corpus", "critic_cls"),
    [(c, k) for c, k, s in CASES if s == "dev"],
    ids=lambda x: getattr(x, "name", ""),
)
def test_assert_rubric_fixtures_passes_over_the_whole_corpus(
    corpus: Corpus, critic_cls: type[LLMCritic]
) -> None:
    """PB3's S2 gate, verbatim, over dev and held-out together."""
    assert_rubric_fixtures(_critic(corpus, critic_cls), corpus.rubric_path, corpus.parse)


def test_replay_hint_names_the_command() -> None:
    assert "PB5_SPLIT" in RERECORD_HINT
