"""Proves the PB3 framework satisfies S2 end-to-end using a throwaway demo
critic — not a real one (see PB5-PB8) — and that the harness itself would
actually catch a regression, not just rubber-stamp a passing critic.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import BaseModel

from probative.core.critic import Finding
from probative.critics.rubric import load_rubric
from probative.critics.testing import assert_rubric_fixtures
from tests.critics._example import NonEmptyTextCritic, parse_notes
from tests.critics._paths import FIXTURES

RUBRIC_PATH = FIXTURES / "example" / "rubric.yaml"


def test_example_critic_satisfies_s2_contract() -> None:
    critic = NonEmptyTextCritic(load_rubric(RUBRIC_PATH))
    assert_rubric_fixtures(critic, RUBRIC_PATH, parse_notes)


class _RegressedCritic(NonEmptyTextCritic):
    """Always passes — simulates a critic that regressed to a no-op."""

    def check(self, candidates: Sequence[BaseModel]) -> list[Finding]:
        return []


def test_assert_rubric_fixtures_fails_loudly_on_a_regressed_critic() -> None:
    critic = _RegressedCritic(load_rubric(RUBRIC_PATH))
    with pytest.raises(AssertionError):
        assert_rubric_fixtures(critic, RUBRIC_PATH, parse_notes)


def test_assert_rubric_fixtures_raises_if_clean_fixtures_glob_matches_nothing() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    empty_glob_rubric = rubric.model_copy(update={"clean_fixtures": "fixtures/clean/nope_*.json"})
    critic = NonEmptyTextCritic(empty_glob_rubric)
    with pytest.raises(AssertionError, match="clean_fixtures glob matched no files"):
        assert_rubric_fixtures(critic, RUBRIC_PATH, parse_notes)


def test_assert_rubric_fixtures_raises_if_defect_fixtures_glob_matches_nothing() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    empty_glob_rubric = rubric.model_copy(update={"defect_fixtures": "fixtures/seeded/nope_*.json"})
    critic = NonEmptyTextCritic(empty_glob_rubric)
    with pytest.raises(AssertionError, match="defect_fixtures glob matched no files"):
        assert_rubric_fixtures(critic, RUBRIC_PATH, parse_notes)
