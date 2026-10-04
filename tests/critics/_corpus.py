"""The two built-in critics' corpora, in one place for the PB5 tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from probative.core.critic import Rubric
from probative.critics import invest, space_warden
from probative.critics.rubric import load_rubric
from tests.critics._candidates import needs, parse_need_fixture, parse_story_fixture, stories


@dataclass(frozen=True)
class Corpus:
    name: str
    rubric_path: Path
    candidate_key: str  # the fixture JSON field holding the quotes
    parse: Callable[[Path], Sequence[BaseModel]]
    build: Callable[..., Sequence[BaseModel]]  # (text, quotes, *, source_id=...) -> candidates

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
CORPORA = [SPACE_WARDEN, INVEST]
SPLITS = ("dev", "held_out")
