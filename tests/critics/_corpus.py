"""The two built-in critics' corpora, in one place for the PB5 tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from probative.core.critic import Rubric
from probative.critics import (
    dependency_critic,
    evidence_auditor,
    invest,
    red_team,
    segment_skeptic,
    space_warden,
)
from probative.critics.rubric import load_rubric
from tests.critics._candidates import (
    build_statement_fixture,
    claims,
    dependencies,
    needs,
    parse_claim_fixture,
    parse_dependency_fixture,
    parse_need_fixture,
    parse_segment_fixture,
    parse_statement_fixture,
    parse_story_fixture,
    segments,
    stories,
)


@dataclass(frozen=True)
class Corpus:
    name: str
    rubric_path: Path
    candidate_key: str  # the fixture JSON field holding the quotes
    parse: Callable[[Path], Sequence[BaseModel]]
    build: Callable[..., Sequence[BaseModel]]  # (text, quotes, *, source_id=...) -> candidates
    # Optional (PB8): builds from the whole fixture dict when a fixture holds more than one
    # candidate kind. Default: `build(text, data[candidate_key])`.
    build_fixture: Callable[..., Sequence[BaseModel]] | None = None

    def build_from(self, data: dict[str, Any], *, source_id: str) -> Sequence[BaseModel]:
        if self.build_fixture is not None:
            return self.build_fixture(data, source_id=source_id)
        return self.build(data["text"], data[self.candidate_key], source_id=source_id)

    @property
    def rubric(self) -> Rubric:
        return load_rubric(self.rubric_path)

    @property
    def root(self) -> Path:
        return self.rubric_path.parent / "fixtures"

    def stress_files(self) -> list[Path]:
        """Hard cases outside the rubric's S2 globs (see generate_pb5.py)."""
        return sorted((self.rubric_path.parent / "stress").glob("*.json"))

    def files(self, polarity: str, split: str) -> list[Path]:
        return sorted((self.root / polarity / split).glob("*.json"))


SPACE_WARDEN = Corpus("space_warden", space_warden.RUBRIC_PATH, "needs", parse_need_fixture, needs)
INVEST = Corpus("invest", invest.RUBRIC_PATH, "stories", parse_story_fixture, stories)
EVIDENCE_AUDITOR = Corpus(
    "evidence_auditor", evidence_auditor.RUBRIC_PATH, "claims", parse_claim_fixture, claims
)
SEGMENT_SKEPTIC = Corpus(
    "segment_skeptic", segment_skeptic.RUBRIC_PATH, "segments", parse_segment_fixture, segments
)
DEPENDENCY_CRITIC = Corpus(
    "dependency_critic",
    dependency_critic.RUBRIC_PATH,
    "dependencies",
    parse_dependency_fixture,
    dependencies,
)
RED_TEAM = Corpus(
    "red_team",
    red_team.RUBRIC_PATH,
    "claims",
    parse_statement_fixture,
    claims,
    build_fixture=build_statement_fixture,
)
CORPORA = [SPACE_WARDEN, INVEST, EVIDENCE_AUDITOR, SEGMENT_SKEPTIC, DEPENDENCY_CRITIC]
SPLITS = ("dev", "held_out")
