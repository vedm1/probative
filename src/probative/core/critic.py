"""Critic framework types (docs/DESIGN.md §9.1, §13; PROBATIVE_PHASE_SPECS.md
PB3): the rubric shape a critic is configured from (S2), and what a critic
returns.

A `Critic` is not an `Agent` (S1): it never proposes a patch and never
touches the graph. It only returns `Finding`s, which the runtime's critic
fan-out (PB12) attaches to a patch under review.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from probative.core.evidence import EvidenceSpan


class Severity(StrEnum):
    """How much authority a Finding carries (docs/DESIGN.md §9.1)."""

    BLOCK = "block"
    WARN = "warn"
    NOTE = "note"


class RubricCheck(BaseModel):
    """One named check within a rubric (S2).

    `severity` is optional (added in PB5): unset, the check inherits the
    rubric's severity; set, it overrides it, so a rubric can say "block on
    this check, warn on the rest" as data rather than in critic code.
    """

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    examples_bad: list[str] = Field(default_factory=list)
    examples_good: list[str] = Field(default_factory=list)
    remedy: str = Field(min_length=1)
    severity: Severity | None = None


class Rubric(BaseModel):
    """A critic's configuration, loaded from YAML (S2).

    `clean_fixtures`/`defect_fixtures` are globs relative to the rubric
    file's own directory, resolved by `probative.critics.rubric`.
    """

    id: str = Field(min_length=1)
    severity: Severity
    invariant: str | None = None
    applies_to: list[str] = Field(default_factory=list)
    checks: list[RubricCheck] = Field(min_length=1)
    clean_fixtures: str = Field(min_length=1)
    defect_fixtures: str = Field(min_length=1)


class Finding(BaseModel):
    """What a critic emits for one violation of one of its rubric's checks."""

    critic_id: str
    check_id: str
    severity: Severity
    invariant: str | None
    message: str
    remedy: str
    target_id: str | None = None
    evidence: EvidenceSpan | None = None


class DimensionScore(BaseModel):
    """One rubric's aggregate result over a batch of Findings
    (`probative.critics.scoring.score_dimension`)."""

    critic_id: str
    invariant: str | None
    blocked: bool
    score: float
    findings: list[Finding]


class RubricError(Exception):
    """Base for rubric-loading failures. Always names the offending file."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


class RubricNotFoundError(RubricError):
    """The rubric file does not exist."""


class MalformedRubricError(RubricError):
    """The rubric file is not valid YAML, is not a mapping at the top
    level, or fails `Rubric`'s schema."""


class UnknownCheckError(ValueError):
    """A critic referenced a `check_id` its own rubric does not declare —
    an authoring bug, not a rubric-loading failure, so it names the critic
    and check rather than a file path."""

    def __init__(self, critic_id: str, check_id: str) -> None:
        self.critic_id = critic_id
        self.check_id = check_id
        super().__init__(f"{critic_id}: no check {check_id!r} declared in its rubric")
