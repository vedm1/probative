"""The ConstraintCritic corpus (PB7). Unlike PB5/PB6's corpora a fixture here is a
whole *document*: constraints and stories that share one source, because the
critic's question (does a story of the same document trace this obligation?) is
relational.

Fixture JSON: `text`, `constraints` and `stories` (verbatim quotes of `text`),
and `expect_untraced` (the constraint quotes no story traces). Seeded files also
carry `check` and `kind`; stress files `allow_also_untraced` and `why`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from probative.core.candidates import ConstraintCandidate, StoryCandidate
from probative.core.critic import Rubric
from probative.critics import constraint_critic
from probative.critics.rubric import load_rubric
from tests.critics._candidates import constraints, load_fixture, stories


@dataclass(frozen=True)
class TraceDoc:
    constraints: list[ConstraintCandidate]
    stories: list[StoryCandidate]
    expect_untraced: frozenset[str]  # constraint ids
    allow_untraced: frozenset[str]  # constraint ids a hard case tolerates being flagged

    @property
    def candidates(self) -> list[BaseModel]:
        return [*self.constraints, *self.stories]


def build_trace_doc(data: dict[str, Any], *, source_id: str) -> TraceDoc:
    text = data["text"]
    cs = constraints(text, data["constraints"], source_id=source_id)
    ss = stories(text, data["stories"], source_id=source_id)
    by_quote = {c.evidence.text: c.id for c in cs}

    def ids(key: str) -> frozenset[str]:
        return frozenset(by_quote[q] for q in data.get(key, []))

    return TraceDoc(cs, ss, ids("expect_untraced"), ids("allow_also_untraced"))


def parse_trace_doc(path: Path) -> TraceDoc:
    return build_trace_doc(load_fixture(path), source_id=f"src_{path.stem}")


@dataclass(frozen=True)
class TraceCorpus:
    name: str
    rubric_path: Path

    @property
    def rubric(self) -> Rubric:
        return load_rubric(self.rubric_path)

    @property
    def root(self) -> Path:
        return self.rubric_path.parent / "fixtures"

    def stress_files(self) -> list[Path]:
        return sorted((self.rubric_path.parent / "stress").glob("*.json"))

    def files(self, polarity: str, split: str) -> list[Path]:
        return sorted((self.root / polarity / split).glob("*.json"))

    def parse(self, path: Path) -> Sequence[BaseModel]:
        return parse_trace_doc(path).candidates

    def quotes(self, path: Path) -> list[str]:
        data = load_fixture(path)
        return [*data["constraints"], *data["stories"]]


CONSTRAINT_CRITIC = TraceCorpus("constraint_critic", constraint_critic.RUBRIC_PATH)
