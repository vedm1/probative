"""Build typed candidates the way production does: a quote resolved against an
in-memory `Source` by PB4's own resolver, never hand-built spans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from probative.core.candidates import (
    CandidateKind,
    ClaimCandidate,
    ConstraintCandidate,
    DependencyCandidate,
    ForecastCandidate,
    NeedCandidate,
    SegmentCandidate,
    StoryCandidate,
    candidate_id,
)
from probative.core.evidence import Source
from probative.extract.resolve import resolve_quote
from tests.extract._helpers import make_source


def _resolve(source: Source, quote: str) -> Any:
    span = resolve_quote(
        source, quote, window=(0, len(source.text)), claimed=set(), max_quote_chars=10_000
    )
    assert not isinstance(span, str), f"fixture quote does not resolve in its own text: {quote!r}"
    return span


def needs(text: str, quotes: list[str], *, source_id: str = "src_test") -> list[NeedCandidate]:
    source = make_source(text, source_id=source_id)
    out = []
    for quote in quotes:
        span = _resolve(source, quote)
        out.append(NeedCandidate(id=candidate_id(CandidateKind.NEED, span), evidence=span))
    return out


def claims(text: str, quotes: list[str], *, source_id: str = "src_test") -> list[ClaimCandidate]:
    source = make_source(text, source_id=source_id)
    out = []
    for quote in quotes:
        span = _resolve(source, quote)
        out.append(ClaimCandidate(id=candidate_id(CandidateKind.CLAIM, span), evidence=span))
    return out


def forecasts(
    text: str, quotes: list[str], *, source_id: str = "src_test"
) -> list[ForecastCandidate]:
    source = make_source(text, source_id=source_id)
    out = []
    for quote in quotes:
        span = _resolve(source, quote)
        out.append(ForecastCandidate(id=candidate_id(CandidateKind.FORECAST, span), evidence=span))
    return out


def stories(text: str, quotes: list[str], *, source_id: str = "src_test") -> list[StoryCandidate]:
    source = make_source(text, source_id=source_id)
    out = []
    for quote in quotes:
        span = _resolve(source, quote)
        out.append(StoryCandidate(id=candidate_id(CandidateKind.STORY, span), evidence=span))
    return out


def segments(
    text: str, quotes: list[str], *, source_id: str = "src_test"
) -> list[SegmentCandidate]:
    source = make_source(text, source_id=source_id)
    out = []
    for quote in quotes:
        span = _resolve(source, quote)
        out.append(SegmentCandidate(id=candidate_id(CandidateKind.SEGMENT, span), evidence=span))
    return out


def constraints(
    text: str, quotes: list[str], *, source_id: str = "src_test"
) -> list[ConstraintCandidate]:
    source = make_source(text, source_id=source_id)
    out = []
    for quote in quotes:
        span = _resolve(source, quote)
        out.append(
            ConstraintCandidate(id=candidate_id(CandidateKind.CONSTRAINT, span), evidence=span)
        )
    return out


def dependencies(
    text: str, quotes: list[str], *, source_id: str = "src_test"
) -> list[DependencyCandidate]:
    source = make_source(text, source_id=source_id)
    out = []
    for quote in quotes:
        span = _resolve(source, quote)
        out.append(
            DependencyCandidate(id=candidate_id(CandidateKind.DEPENDENCY, span), evidence=span)
        )
    return out


def load_fixture(path: Path) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return raw


def fixture_source(path: Path) -> Source:
    return make_source(load_fixture(path)["text"], source_id=f"src_{path.stem}")


def parse_need_fixture(path: Path) -> list[NeedCandidate]:
    data = load_fixture(path)
    return needs(data["text"], data["needs"], source_id=f"src_{path.stem}")


def parse_story_fixture(path: Path) -> list[StoryCandidate]:
    data = load_fixture(path)
    return stories(data["text"], data["stories"], source_id=f"src_{path.stem}")


def parse_claim_fixture(path: Path) -> list[ClaimCandidate]:
    data = load_fixture(path)
    return claims(data["text"], data["claims"], source_id=f"src_{path.stem}")


def parse_dependency_fixture(path: Path) -> list[DependencyCandidate]:
    data = load_fixture(path)
    return dependencies(data["text"], data["dependencies"], source_id=f"src_{path.stem}")


def parse_segment_fixture(path: Path) -> list[SegmentCandidate]:
    data = load_fixture(path)
    return segments(data["text"], data["segments"], source_id=f"src_{path.stem}")


def build_statement_fixture(
    data: dict[str, Any], *, source_id: str
) -> list[ClaimCandidate | ForecastCandidate]:
    """RedTeam fixtures hold claim quotes under `claims` and forecast quotes under
    `forecasts` (either may be absent), resolved in the one fixture text."""
    return [
        *claims(data["text"], data.get("claims", []), source_id=source_id),
        *forecasts(data["text"], data.get("forecasts", []), source_id=source_id),
    ]


def parse_statement_fixture(path: Path) -> list[ClaimCandidate | ForecastCandidate]:
    return build_statement_fixture(load_fixture(path), source_id=f"src_{path.stem}")
