"""Critic framework (PROBATIVE_PHASE_SPECS.md PB3): a critic is a rubric
file (S2) plus a `Critic` subclass with one method — `check`.

Public API: `Critic`, `load_rubric`, `resolve_fixture_paths`, `run_critics`,
`score_dimension`, `aggregate`, `assert_rubric_fixtures`. The typed shapes
(`Severity`, `Rubric`, `RubricCheck`, `Finding`, `DimensionScore`) live in
`probative.core.critic`.
"""

from __future__ import annotations

from probative.critics.base import Critic
from probative.critics.rubric import load_rubric, resolve_fixture_paths
from probative.critics.runner import run_critics
from probative.critics.scoring import aggregate, score_dimension
from probative.critics.testing import assert_rubric_fixtures

__all__ = [
    "Critic",
    "aggregate",
    "assert_rubric_fixtures",
    "load_rubric",
    "resolve_fixture_paths",
    "run_critics",
    "score_dimension",
]
