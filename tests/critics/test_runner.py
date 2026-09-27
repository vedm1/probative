from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from probative.core.critic import Finding, Rubric, RubricCheck, Severity
from probative.critics.base import Critic
from probative.critics.runner import run_critics


class Alpha(BaseModel):
    id: str


class Beta(BaseModel):
    id: str


def _rubric(rubric_id: str, applies_to: list[str]) -> Rubric:
    return Rubric(
        id=rubric_id,
        severity=Severity.NOTE,
        applies_to=applies_to,
        checks=[RubricCheck(id="c", description="d", remedy="r")],
        clean_fixtures="x",
        defect_fixtures="y",
    )


class _RecordingCritic(Critic):
    def __init__(self, rubric: Rubric) -> None:
        super().__init__(rubric)
        self.seen: list[BaseModel] = []
        self.called = False

    def check(self, candidates: Sequence[BaseModel]) -> list[Finding]:
        self.called = True
        self.seen = list(candidates)
        return [
            self._finding(check_id="c", message=f"flagged {c.id}", target_id=c.id)  # type: ignore[attr-defined]
            for c in candidates
        ]


def test_run_critics_filters_by_applies_to() -> None:
    alpha_critic = _RecordingCritic(_rubric("alpha_critic", ["Alpha"]))
    beta_critic = _RecordingCritic(_rubric("beta_critic", ["Beta"]))
    candidates = [Alpha(id="a1"), Beta(id="b1")]

    findings = run_critics([alpha_critic, beta_critic], candidates)

    assert alpha_critic.seen == [Alpha(id="a1")]
    assert beta_critic.seen == [Beta(id="b1")]
    assert {f.target_id for f in findings} == {"a1", "b1"}


def test_run_critics_empty_applies_to_matches_everything() -> None:
    critic = _RecordingCritic(_rubric("catch_all", []))
    candidates = [Alpha(id="a1"), Beta(id="b1")]

    run_critics([critic], candidates)

    assert critic.seen == candidates


def test_run_critics_no_relevant_candidates_skips_check_call() -> None:
    critic = _RecordingCritic(_rubric("alpha_only", ["Alpha"]))

    findings = run_critics([critic], [Beta(id="b1")])

    assert critic.called is False
    assert findings == []


def test_run_critics_concatenates_multiple_critics() -> None:
    first = _RecordingCritic(_rubric("first", []))
    second = _RecordingCritic(_rubric("second", []))
    candidates = [Alpha(id="a1")]

    findings = run_critics([first, second], candidates)

    assert [f.critic_id for f in findings] == ["first", "second"]
