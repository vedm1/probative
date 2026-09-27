from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import BaseModel

from probative.core.critic import Finding, Severity, UnknownCheckError
from probative.critics.base import Critic
from probative.critics.rubric import load_rubric
from tests.critics._paths import FIXTURES

RUBRIC_PATH = FIXTURES / "example" / "rubric.yaml"


class _NoOpCritic(Critic):
    def check(self, candidates: Sequence[BaseModel]) -> list[Finding]:
        return []


def test_critic_is_abstract() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    with pytest.raises(TypeError):
        Critic(rubric)  # type: ignore[abstract]


def test_finding_helper_populates_from_rubric() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    critic = _NoOpCritic(rubric)
    finding = critic._finding(check_id="non_empty_text", message="something broke", target_id="n1")
    assert finding.critic_id == rubric.id
    assert finding.check_id == "non_empty_text"
    assert finding.severity == rubric.severity
    assert finding.invariant == rubric.invariant
    assert finding.message == "something broke"
    assert finding.remedy == "Fill in the note's text"
    assert finding.target_id == "n1"
    assert finding.evidence is None


def test_finding_helper_severity_override() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    critic = _NoOpCritic(rubric)
    finding = critic._finding(
        check_id="non_empty_text", message="escalated", severity=Severity.BLOCK
    )
    assert finding.severity == Severity.BLOCK


def test_finding_helper_unknown_check_id_raises() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    critic = _NoOpCritic(rubric)
    with pytest.raises(UnknownCheckError) as exc_info:
        critic._finding(check_id="nonexistent", message="bug")
    assert exc_info.value.critic_id == rubric.id
    assert exc_info.value.check_id == "nonexistent"
