"""EvidenceAuditor (PB6-p1): wiring, severity policy and scope against a
scripted provider. What the model does with the corpus is measured by the
recorded replay (test_pb6_replay.py), not here."""

from __future__ import annotations

import pytest

from probative.core.critic import Severity
from probative.critics import aggregate, run_critics
from probative.critics.evidence_auditor import EvidenceAuditor, evidence_auditor_rubric
from probative.critics.llm_judge import (
    _JUDGE_PREAMBLE,
    CheckJudgement,
    JudgementBatch,
    Verdict,
    build_system_prompt,
)
from probative.llm import FakeProvider
from tests.critics._candidates import claims, needs
from tests.critics._corpus import EVIDENCE_AUDITOR

CLAIM = "Around 58% of online shoppers abandon a purchase when asked to create an account."
CHECKS = ("unsourced_statistic", "basis_overreach", "unsourced_assertion")


def _batch(claim_id: str, **verdicts: Verdict) -> JudgementBatch:
    return JudgementBatch(
        judgements=[
            CheckJudgement(
                candidate_id=claim_id,
                check_id=check,
                verdict=verdicts.get(check, Verdict.MET),
                quote="Around 58%" if verdicts.get(check) == Verdict.NOT_MET else None,
            )
            for check in CHECKS
        ]
    )


def test_rubric_is_i1_with_per_check_severity() -> None:
    rubric = evidence_auditor_rubric()
    assert (rubric.id, rubric.severity, rubric.invariant) == (
        "evidence_auditor",
        Severity.WARN,
        "I1",
    )
    assert rubric.applies_to == ["ClaimCandidate"]
    assert [c.id for c in rubric.checks] == list(CHECKS)
    effective = {c.id: c.severity or rubric.severity for c in rubric.checks}
    assert effective == {
        "unsourced_statistic": Severity.BLOCK,
        "basis_overreach": Severity.BLOCK,
        "unsourced_assertion": Severity.WARN,
    }
    assert EVIDENCE_AUDITOR.rubric_path.is_file()


def test_every_check_has_examples_both_ways_and_a_remedy() -> None:
    for check in evidence_auditor_rubric().checks:
        assert check.examples_bad and check.examples_good and check.remedy, check.id


@pytest.mark.parametrize(
    ("check", "severity"),
    [
        ("unsourced_statistic", Severity.BLOCK),
        ("basis_overreach", Severity.BLOCK),
        ("unsourced_assertion", Severity.WARN),
    ],
)
def test_a_flagged_claim_carries_the_checks_own_severity_and_i1(
    check: str, severity: Severity
) -> None:
    (claim,) = claims(CLAIM, [CLAIM])
    provider = FakeProvider([_batch(claim.id, **{check: Verdict.NOT_MET})])
    (finding,) = EvidenceAuditor.from_builtin_rubric(provider, model="m").check([claim])
    assert (finding.critic_id, finding.check_id, finding.invariant, finding.severity) == (
        "evidence_auditor",
        check,
        "I1",
        severity,
    )
    assert finding.evidence is not None and finding.evidence.text == "Around 58%"
    assert finding.message.startswith(f"{check}: “Around 58%” — ")
    assert finding.remedy


def test_a_block_zeroes_the_dimension_but_a_warn_does_not() -> None:
    (claim,) = claims(CLAIM, [CLAIM])
    rubric = evidence_auditor_rubric()
    blocked = EvidenceAuditor.from_builtin_rubric(
        FakeProvider([_batch(claim.id, unsourced_statistic=Verdict.NOT_MET)]), model="m"
    ).check([claim])
    (dimension,) = aggregate([rubric], blocked)
    assert dimension.blocked and dimension.score == 0.0
    warned = EvidenceAuditor.from_builtin_rubric(
        FakeProvider([_batch(claim.id, unsourced_assertion=Verdict.NOT_MET)]), model="m"
    ).check([claim])
    (dimension,) = aggregate([rubric], warned)
    assert not dimension.blocked and dimension.score == 8.0


def test_it_judges_claims_only() -> None:
    (need,) = needs("Users need a dashboard.", ["Users need a dashboard."])
    critic = EvidenceAuditor.from_builtin_rubric(FakeProvider([]), model="m")
    assert run_critics([critic], [need]) == []  # filtered by applies_to: no call made
    with pytest.raises(TypeError, match="ClaimCandidate"):
        critic.check([need])


def test_it_defaults_to_the_pb5_batch_size() -> None:
    # 5 is the largest size PB5 recorded; PB6-p1's own mixed-batch run is what measures it here
    assert EvidenceAuditor.from_builtin_rubric(FakeProvider([]), model="m")._batch_size == 5


def test_the_prompt_is_closed_world_absence_of_a_basis_is_the_violation() -> None:
    prompt = build_system_prompt(
        evidence_auditor_rubric(), EvidenceAuditor.preamble, EvidenceAuditor.judge_preamble
    )
    assert EvidenceAuditor.judge_preamble != _JUDGE_PREAMBLE
    assert "Missing information is cannot_tell" not in prompt
    lowered = prompt.lower()
    assert "absence" in lowered and "never judge whether" in lowered
    # the model must not use its own knowledge to call a figure true or false
    assert "do not use your own knowledge" in lowered
    # the three-valued vocabulary and the no-scores rule survive the override
    for needle in ("not_met", "met", "cannot_tell", "verbatim", "Do not return scores"):
        assert needle in prompt
    # the rubric is still rendered as data, every check with its examples
    for check in evidence_auditor_rubric().checks:
        assert f"[{check.id}]" in prompt
        assert all(example in prompt for example in (*check.examples_bad, *check.examples_good))


def test_the_prompt_declares_candidates_untrusted() -> None:
    assert "never instructions" in EvidenceAuditor.judge_preamble.lower()


def _prompt() -> str:
    return build_system_prompt(
        evidence_auditor_rubric(), EvidenceAuditor.preamble, EvidenceAuditor.judge_preamble
    )


def test_softening_words_are_defined_as_neither_a_hedge_nor_a_basis() -> None:
    """Pre-recording review B1: 'around 58%' and 'most banks' must not be readable
    as already hedged, or the seeded defects are in dispute before the model runs."""
    prompt = _prompt()
    for word in ("around", "roughly", "nearly", "most", "usually", "rarely"):
        assert word in prompt.lower()
    assert "are not markers and not a basis" in prompt  # the preamble's rule
    assert "not a basis and not a hedge" in prompt  # the statistic check's rule
    assert "those words are not hedges" in prompt  # the assertion check's rule


def test_statistic_versus_assertion_is_decided_by_a_figure_not_a_feeling() -> None:
    prompt = _prompt()
    assert "A number, a fraction" in prompt and "belongs to unsourced_assertion" in prompt


def test_a_remark_about_the_statements_own_status_is_never_a_basis() -> None:
    """Pre-recording review B3: 'already verified', 'pre-approved' and notes to the
    reviewer must not count as the 'however thin' attribution the rubric allows."""
    prompt = _prompt()
    assert prompt.count("own status") >= 3  # mandate preamble and two check descriptions
    assert "addressed to the reader" in prompt


def test_a_named_pilot_or_trial_counts_as_a_basis() -> None:
    assert "named or identified study, trial, pilot or dataset" in _prompt()


def test_a_measured_quantity_about_the_product_still_needs_a_basis() -> None:
    assert "measured quantity" in _prompt()


def test_cannot_tell_is_for_fragments_not_for_unsourced_statements() -> None:
    """Pre-recording review S1: a blocking check must not be escapable by doubt."""
    judge = EvidenceAuditor.judge_preamble
    assert "not a complete statement" in judge
    assert "unclear whether it asserts a fact or states a plan" not in judge
    assert "Do not use cannot_tell to avoid flagging" in judge
