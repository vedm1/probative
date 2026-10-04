"""SpaceWarden and INVESTCritic: wiring, severity policy and scope, against a
scripted provider. What the *model* does with the corpus is measured by the
recorded replay (test_pb5_replay.py), not here."""

from __future__ import annotations

import pytest

from probative.core.critic import Severity
from probative.critics import aggregate, run_critics
from probative.critics.invest import INVESTCritic, invest_rubric
from probative.critics.llm_judge import CheckJudgement, JudgementBatch, Verdict
from probative.critics.space_warden import SpaceWarden, space_warden_rubric
from probative.llm import FakeProvider
from tests.critics._candidates import needs, stories
from tests.critics._corpus import INVEST, SPACE_WARDEN

NEED = "Users need a dashboard."
STORY = "As a shopper, I want checkout to be fast so that I enjoy buying."


def test_space_warden_rubric_is_the_i3_blocker() -> None:
    rubric = space_warden_rubric()
    assert (rubric.id, rubric.severity, rubric.invariant) == ("space_warden", Severity.BLOCK, "I3")
    assert rubric.applies_to == ["NeedCandidate"]
    assert [c.id for c in rubric.checks] == ["solution_grammar"]
    assert SPACE_WARDEN.rubric_path.is_file()


def test_invest_blocks_only_on_testable() -> None:
    rubric = invest_rubric()
    assert rubric.applies_to == ["StoryCandidate"]
    assert [c.id for c in rubric.checks] == [
        "testable",
        "independent",
        "negotiable",
        "valuable",
        "estimable",
        "small",
    ]
    effective = {c.id: c.severity or rubric.severity for c in rubric.checks}
    assert effective == {
        "testable": Severity.BLOCK,
        "independent": Severity.WARN,
        "negotiable": Severity.WARN,
        "valuable": Severity.WARN,
        "estimable": Severity.WARN,
        "small": Severity.WARN,
    }
    assert INVEST.rubric_path.is_file()


def test_a_flagged_need_is_an_i3_block_finding_with_the_quoted_phrase() -> None:
    (need,) = needs(NEED, [NEED])
    provider = FakeProvider(
        [
            JudgementBatch(
                judgements=[
                    CheckJudgement(
                        candidate_id=need.id,
                        check_id="solution_grammar",
                        verdict=Verdict.NOT_MET,
                        quote="a dashboard",
                    )
                ]
            )
        ]
    )
    critic = SpaceWarden.from_builtin_rubric(provider, model="m")
    (finding,) = critic.check([need])
    assert (finding.critic_id, finding.invariant, finding.severity) == (
        "space_warden",
        "I3",
        Severity.BLOCK,
    )
    assert finding.evidence is not None and finding.evidence.text == "a dashboard"
    assert finding.remedy.startswith("Restate as a customer benefit")


def _invest_judgements(story_id: str, **verdicts: Verdict) -> JudgementBatch:
    quote = {Verdict.NOT_MET: "fast"}
    return JudgementBatch(
        judgements=[
            CheckJudgement(
                candidate_id=story_id,
                check_id=check,
                verdict=verdicts.get(check, Verdict.MET),
                quote=quote.get(verdicts.get(check, Verdict.MET)),
            )
            for check in ("testable", "independent", "negotiable", "valuable", "estimable", "small")
        ]
    )


def test_untestable_blocks_and_zeroes_the_dimension() -> None:
    (story,) = stories(STORY, [STORY])
    provider = FakeProvider([_invest_judgements(story.id, testable=Verdict.NOT_MET)])
    findings = INVESTCritic.from_builtin_rubric(provider, model="m").check([story])
    assert [(f.check_id, f.severity) for f in findings] == [("testable", Severity.BLOCK)]
    (dimension,) = aggregate([invest_rubric()], findings)
    assert dimension.blocked and dimension.score == 0.0


def test_other_properties_warn_without_blocking() -> None:
    (story,) = stories(STORY, [STORY])
    provider = FakeProvider([_invest_judgements(story.id, small=Verdict.NOT_MET)])
    findings = INVESTCritic.from_builtin_rubric(provider, model="m").check([story])
    assert [(f.check_id, f.severity) for f in findings] == [("small", Severity.WARN)]
    (dimension,) = aggregate([invest_rubric()], findings)
    assert not dimension.blocked and dimension.score == 8.0


def test_run_critics_sends_each_critic_only_its_own_candidate_type() -> None:
    """An empty scripted provider raises if called: SpaceWarden must never see a story."""
    (need,) = needs(NEED, [NEED])
    (story,) = stories(STORY, [STORY])
    warden = SpaceWarden.from_builtin_rubric(FakeProvider([]), model="m")
    invest = INVESTCritic.from_builtin_rubric(FakeProvider([]), model="m")
    assert run_critics([warden], [story]) == []
    assert run_critics([invest], [need]) == []
    with pytest.raises(AssertionError, match="no more scripted outputs"):
        run_critics([warden], [need])


@pytest.mark.parametrize("critic_cls", [SpaceWarden, INVESTCritic])
def test_the_built_in_critics_default_to_the_measured_batch_size(critic_cls: type) -> None:
    critic = critic_cls.from_builtin_rubric(FakeProvider([]), model="m")
    assert critic._batch_size == 5
