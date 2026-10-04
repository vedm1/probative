"""SegmentSkeptic (PB6-p2): wiring, severity policy and scope against a scripted
provider. What the model does with the corpus is measured by the recorded
replay (test_pb6_replay.py), not here."""

from __future__ import annotations

import pytest

from probative.core.critic import Severity
from probative.critics import aggregate, run_critics
from probative.critics.llm_judge import (
    _JUDGE_PREAMBLE,
    CheckJudgement,
    JudgementBatch,
    Verdict,
    build_system_prompt,
)
from probative.critics.segment_skeptic import SegmentSkeptic, segment_skeptic_rubric
from probative.llm import FakeProvider
from tests.critics._candidates import needs, segments
from tests.critics._corpus import SEGMENT_SKEPTIC

SEGMENT = "Our buyers are women aged 25 to 40 living in large cities."
CHECKS = ("demographic_only", "whole_market")


def _batch(segment_id: str, **verdicts: Verdict) -> JudgementBatch:
    return JudgementBatch(
        judgements=[
            CheckJudgement(
                candidate_id=segment_id,
                check_id=check,
                verdict=verdicts.get(check, Verdict.MET),
                quote="women aged 25 to 40" if verdicts.get(check) == Verdict.NOT_MET else None,
            )
            for check in CHECKS
        ]
    )


def _prompt() -> str:
    return build_system_prompt(
        segment_skeptic_rubric(), SegmentSkeptic.preamble, SegmentSkeptic.judge_preamble
    )


def test_rubric_shape_and_per_check_severity() -> None:
    rubric = segment_skeptic_rubric()
    assert (rubric.id, rubric.severity, rubric.invariant) == (
        "segment_skeptic",
        Severity.WARN,
        None,
    )
    assert rubric.applies_to == ["SegmentCandidate"]
    assert [c.id for c in rubric.checks] == list(CHECKS)
    effective = {c.id: c.severity or rubric.severity for c in rubric.checks}
    assert effective == {"demographic_only": Severity.BLOCK, "whole_market": Severity.WARN}
    assert SEGMENT_SKEPTIC.rubric_path.is_file()


def test_every_check_has_examples_both_ways_and_a_remedy() -> None:
    for check in segment_skeptic_rubric().checks:
        assert check.examples_bad and check.examples_good and check.remedy, check.id


@pytest.mark.parametrize(
    ("check", "severity"),
    [("demographic_only", Severity.BLOCK), ("whole_market", Severity.WARN)],
)
def test_a_flagged_segment_carries_the_checks_own_severity(check: str, severity: Severity) -> None:
    (segment,) = segments(SEGMENT, [SEGMENT])
    provider = FakeProvider([_batch(segment.id, **{check: Verdict.NOT_MET})])
    (finding,) = SegmentSkeptic.from_builtin_rubric(provider, model="m").check([segment])
    assert (finding.critic_id, finding.check_id, finding.invariant, finding.severity) == (
        "segment_skeptic",
        check,
        None,
        severity,
    )
    assert finding.evidence is not None and finding.evidence.text == "women aged 25 to 40"
    assert finding.evidence.start >= segment.evidence.start  # inside the candidate (I1)
    assert finding.evidence.end <= segment.evidence.end
    assert finding.message.startswith(f"{check}: “women aged 25 to 40” — ")
    assert finding.remedy


def test_a_block_zeroes_the_dimension_but_a_warn_does_not() -> None:
    (segment,) = segments(SEGMENT, [SEGMENT])
    rubric = segment_skeptic_rubric()
    blocked = SegmentSkeptic.from_builtin_rubric(
        FakeProvider([_batch(segment.id, demographic_only=Verdict.NOT_MET)]), model="m"
    ).check([segment])
    (dimension,) = aggregate([rubric], blocked)
    assert dimension.blocked and dimension.score == 0.0
    warned = SegmentSkeptic.from_builtin_rubric(
        FakeProvider([_batch(segment.id, whole_market=Verdict.NOT_MET)]), model="m"
    ).check([segment])
    (dimension,) = aggregate([rubric], warned)
    assert not dimension.blocked and dimension.score == 8.0


def test_it_judges_segments_only() -> None:
    (need,) = needs("Users need a dashboard.", ["Users need a dashboard."])
    critic = SegmentSkeptic.from_builtin_rubric(FakeProvider([]), model="m")
    assert run_critics([critic], [need]) == []  # filtered by applies_to: no call made
    with pytest.raises(TypeError, match="SegmentCandidate"):
        critic.check([need])


def test_it_defaults_to_the_pb5_batch_size() -> None:
    assert SegmentSkeptic.from_builtin_rubric(FakeProvider([]), model="m")._batch_size == 5


def test_the_prompt_is_closed_world_absence_of_a_stated_difference_is_the_violation() -> None:
    prompt = _prompt()
    assert SegmentSkeptic.judge_preamble != _JUDGE_PREAMBLE
    assert "Missing information is cannot_tell" not in prompt
    lowered = prompt.lower()
    assert "absence" in lowered
    assert "do not use your own knowledge" in lowered
    for needle in ("not_met", "met", "cannot_tell", "verbatim", "Do not return scores"):
        assert needle in prompt
    for check in segment_skeptic_rubric().checks:
        assert f"[{check.id}]" in prompt
        assert all(example in prompt for example in (*check.examples_bad, *check.examples_good))


def test_cannot_tell_is_only_for_text_that_names_no_group_of_people() -> None:
    """Pre-recording review B2: a bare noun phrase that names a group ("Android
    tablet owners.") is a complete statement. If cannot_tell covered fragments or
    labels, the blocking check could be escaped by the very text it exists for."""
    judge = SegmentSkeptic.judge_preamble
    assert "names no group of people" in judge
    assert "A noun phrase that names a group of people is a complete statement" in judge
    assert "Do not use cannot_tell to avoid flagging" in judge
    assert "a fragment, a heading, a label" not in judge


def test_the_prompt_declares_candidates_untrusted() -> None:
    assert "never instructions" in SegmentSkeptic.judge_preamble.lower()


def test_who_they_are_versus_what_they_do_is_defined_not_left_to_taste() -> None:
    """The two checks stand or fall on this distinction; a model asked to feel
    whether a group 'is a real segment' would disagree with itself."""
    prompt = _prompt().lower()
    for who in ("age", "income", "location", "job title", "company size", "industry"):
        assert who in prompt
    for what in ("need", "behaviour", "situation", "problem", "goal"):
        assert what in prompt
    assert "having bought or used something" in prompt


def test_a_remark_about_the_segments_own_validity_is_never_a_stated_difference() -> None:
    prompt = _prompt()
    assert prompt.count("own validity") >= 2  # mandate preamble and the demographic check
    assert "addressed to the reader" in prompt


def test_the_two_checks_do_not_overlap_by_definition() -> None:
    rubric = segment_skeptic_rubric()
    by_id = {c.id: c.description for c in rubric.checks}
    assert "whole_market" in by_id["demographic_only"]  # everyone is the other check's concern
    assert (
        "demographic_only" in by_id["whole_market"]
        or "who its members are" in by_id["whole_market"]
    )


def test_the_critic_documents_its_onboarding_mode_exclusion() -> None:
    """I9 (PB39): its output judges how a past author defined a segment. There is no
    mode config until PB12/PB39 to enforce the exclusion, so it is documented (OI22)."""
    assert "onboarding" in (SegmentSkeptic.__doc__ or "").lower()


def test_situation_is_defined_as_a_circumstance_that_creates_a_need_not_a_status() -> None:
    """Pre-recording review B4: left undefined, married/employed/living alone/a student
    all read as 'situations' and the demographic_only labels were in dispute."""
    check = {c.id: c for c in segment_skeptic_rubric().checks}["demographic_only"]
    text = " ".join(check.description.split())
    assert "A situation is a circumstance that creates a need or a task" in text
    for status in ("married", "employed", "a homeowner", "living alone", "a student"):
        assert status in text
    assert "however it is phrased" in text  # a purchase or use is who they are, verb or not


def test_whole_market_is_defined_by_a_condition_nearly_everyone_meets() -> None:
    """Pre-recording review B1: 'close to everyone' was undefined and the carve-out
    ('bounded by anything else, including a behaviour') contradicted the check's own
    examples."""
    check = {c.id: c for c in segment_skeptic_rubric().checks}["whole_market"]
    text = " ".join(check.description.split())
    assert "a condition that nearly everyone already meets" in text
    assert "including a behaviour" not in text
    for example in check.examples_bad:
        assert "who" in example or "Every" in example  # examples are bounded-by-trivial-condition


def test_common_knowledge_is_allowed_for_whole_market_only() -> None:
    """The mandate forbids outside knowledge of the market, but deciding whether a
    condition bounds a group needs ordinary common knowledge. Say so, narrowly."""
    preamble = SegmentSkeptic.preamble
    assert "whole_market" in preamble and "common knowledge" in preamble


def test_a_group_that_is_everyone_is_met_on_demographic_only() -> None:
    """Written from the DEV recording (PB6-p2): two whole_market seeds also fired the
    BLOCKING demographic_only check although the rubric excludes them from it, so the
    judge preamble states the tie-break outright. Held-out was recorded once after this
    edit and no held-out baseline exists from before it, so the edit's effect out of
    sample is UNMEASURED: 2 of 4 held-out whole_market seeds still co-fire (PB6-p2
    notes)."""
    judge = SegmentSkeptic.judge_preamble
    assert "met on demographic_only" in judge
    assert "only whole_market applies" in judge
