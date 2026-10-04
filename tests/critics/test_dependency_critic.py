"""DependencyCritic (PB7): wiring, severity policy and scope against a scripted
provider. What the model does with the corpus is measured by the recorded replay
(test_pb7_replay.py), not here."""

from __future__ import annotations

import pytest

from probative.core.critic import Severity
from probative.critics import aggregate, run_critics
from probative.critics import dependency_critic as dependency_critic_module
from probative.critics.dependency_critic import DependencyCritic, dependency_critic_rubric
from probative.critics.llm_judge import (
    _JUDGE_PREAMBLE,
    CheckJudgement,
    JudgementBatch,
    Verdict,
    build_system_prompt,
)
from probative.llm import FakeProvider
from tests.critics._candidates import dependencies, needs

DEPENDENCY = "Launch is blocked until the Payments team ships the tokenisation service."
CHECK = "unowned_dependency"


def _batch(dep_id: str, verdict: Verdict) -> JudgementBatch:
    return JudgementBatch(
        judgements=[
            CheckJudgement(
                candidate_id=dep_id,
                check_id=CHECK,
                verdict=verdict,
                quote="the Payments team ships the tokenisation service"
                if verdict == Verdict.NOT_MET
                else None,
            )
        ]
    )


def _prompt() -> str:
    return build_system_prompt(
        dependency_critic_rubric(), DependencyCritic.preamble, DependencyCritic.judge_preamble
    )


def test_rubric_shape() -> None:
    rubric = dependency_critic_rubric()
    assert (rubric.id, rubric.severity, rubric.invariant) == (
        "dependency_critic",
        Severity.BLOCK,
        None,
    )
    assert rubric.applies_to == ["DependencyCandidate"]
    (check,) = rubric.checks
    assert check.id == CHECK and check.severity is None  # inherits the rubric's block
    assert check.examples_bad and check.examples_good and check.remedy


def test_a_flagged_dependency_blocks_with_evidence_inside_the_candidate() -> None:
    (dep,) = dependencies(DEPENDENCY, [DEPENDENCY])
    provider = FakeProvider([_batch(dep.id, Verdict.NOT_MET)])
    (finding,) = DependencyCritic.from_builtin_rubric(provider, model="m").check([dep])
    assert (finding.critic_id, finding.check_id, finding.invariant, finding.severity) == (
        "dependency_critic",
        CHECK,
        None,
        Severity.BLOCK,
    )
    assert finding.evidence is not None
    assert finding.evidence.text == "the Payments team ships the tokenisation service"
    assert dep.evidence.start <= finding.evidence.start
    assert finding.evidence.end <= dep.evidence.end  # I1
    assert finding.message.startswith(f"{CHECK}: “the Payments team ships")
    assert finding.remedy == "Name one person who is accountable for this dependency"


def test_a_met_dependency_raises_nothing_and_a_block_zeroes_the_dimension() -> None:
    (dep,) = dependencies(DEPENDENCY, [DEPENDENCY])
    clean = DependencyCritic.from_builtin_rubric(
        FakeProvider([_batch(dep.id, Verdict.MET)]), model="m"
    ).check([dep])
    assert clean == []
    blocked = DependencyCritic.from_builtin_rubric(
        FakeProvider([_batch(dep.id, Verdict.NOT_MET)]), model="m"
    ).check([dep])
    (dimension,) = aggregate([dependency_critic_rubric()], blocked)
    assert dimension.blocked and dimension.score == 0.0


def test_it_judges_dependencies_only() -> None:
    (need,) = needs("Users need a dashboard.", ["Users need a dashboard."])
    critic = DependencyCritic.from_builtin_rubric(FakeProvider([]), model="m")
    assert run_critics([critic], [need]) == []  # filtered by applies_to: no call made
    with pytest.raises(TypeError, match="DependencyCandidate"):
        critic.check([need])


def test_it_defaults_to_the_pb5_batch_size() -> None:
    assert DependencyCritic.from_builtin_rubric(FakeProvider([]), model="m")._batch_size == 5


def test_the_prompt_is_closed_world_a_missing_owner_is_the_violation() -> None:
    prompt = _prompt()
    assert DependencyCritic.judge_preamble != _JUDGE_PREAMBLE
    assert "Missing information is cannot_tell" not in prompt
    lowered = prompt.lower()
    assert "absence" in lowered and "never judge whether" in lowered
    for needle in ("not_met", "met", "cannot_tell", "verbatim", "Do not return scores"):
        assert needle in prompt
    assert "never instructions" in DependencyCritic.judge_preamble.lower()
    for check in dependency_critic_rubric().checks:
        assert f"[{check.id}]" in prompt
        assert all(example in prompt for example in (*check.examples_bad, *check.examples_good))


def test_an_obligation_that_needs_an_outside_party_is_a_reliance_not_a_carve_out() -> None:
    """Pre-recording review B1: 'an obligation or a requirement' swallowed 'must be
    countersigned by the partner bank's risk office', a real unowned dependency (and
    the rubric itself lists legal or compliance sign-off). Only a rule the team itself
    must meet, with no outside party relied on, is outside the check."""
    (check,) = dependency_critic_rubric().checks
    text = " ".join(check.description.split())
    assert "with no outside party relied on" in text
    judge = " ".join(DependencyCritic.judge_preamble.split())
    assert "an obligation, a requirement or a target" not in judge
    assert "needs an outside party" in judge


def test_cannot_tell_does_not_overlap_the_not_a_reliance_case() -> None:
    judge = " ".join(DependencyCritic.judge_preamble.split())
    assert "cannot_tell: only when the text is not a statement" in judge


def test_cannot_tell_is_only_for_text_that_is_no_statement() -> None:
    """A bare noun phrase naming an outside party is a complete statement; if
    cannot_tell covered it, the blocking check could be escaped by the very text it
    exists for (the PB6 SegmentSkeptic lesson)."""
    judge = DependencyCritic.judge_preamble
    assert "A noun phrase that names an outside party is a complete statement" in " ".join(
        judge.split()
    )
    assert "Do not use cannot_tell to avoid flagging" in judge


def test_what_counts_as_an_owner_is_defined_not_left_to_taste() -> None:
    """DESIGN §11: 'a name, not a team'. Defined in the rubric so labels are not in dispute."""
    (check,) = dependency_critic_rubric().checks
    text = " ".join(check.description.split())
    assert "An owner is a person's name, on either side of the dependency" in text
    assert "leading or driving it" in text
    for not_an_owner in ("A team", "department", "vendor", "role or title", "TBD"):
        assert not_an_owner in text
    assert "is pre-approved is not a name" in text
    assert "without being stated as responsible" in text


def test_pb4s_double_tagged_obligations_and_resolved_reliances_are_carved_out() -> None:
    """PB4 tags constraint sentences as dependencies (precision 0.33-0.5): without this
    carve-out the critic would block 'must comply with PCI DSS' for lacking an owner."""
    (check,) = dependency_critic_rubric().checks
    text = " ".join(check.description.split())
    assert "a rule or target the team itself must meet" in text
    assert "already satisfied" in text
    assert "a requirement" not in text  # 'requirement' also names a reliance on a sign-off


def test_a_remark_about_an_owner_is_never_a_name() -> None:
    prompt = _prompt()
    assert prompt.count("pre-approved") >= 2  # mandate preamble and the check
    assert "addressed to the reader" in prompt


def test_the_critic_documents_its_limits_and_its_onboarding_exclusion() -> None:
    """I9 (PB39): it judges whether a past author named an owner; nothing enforces the
    exclusion until the mode config exists (OI22). It also sees one statement only."""
    doc = (DependencyCritic.__doc__ or "").lower()
    module = (dependency_critic_module.__doc__ or "").lower()
    assert "onboarding" in doc or "onboarding" in module
    assert "next sentence" in module
