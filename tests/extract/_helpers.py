"""Shared builders for the PB4 tests: in-memory `Source`s, so the unit tests
never touch the filesystem (the round-trip tests use real fixture files)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from probative.core.evidence import (
    EvidenceKind,
    Locator,
    LocatorRegion,
    Source,
    SourceFormat,
    Tier,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "extract"
RECORDINGS = FIXTURES / "recordings"
RERECORD_HINT = (
    "Re-record with `ANTHROPIC_API_KEY=... uv run pytest -m live tests/extract/test_live_record.py`"
)


def make_source(
    text: str,
    *,
    regions: list[tuple[int, int, Locator]] | None = None,
    source_id: str = "src_test",
) -> Source:
    """A `Source` over `text`. With no `regions`, one region covers it all."""
    spec = regions if regions is not None else [(0, len(text), Locator())]
    return Source(
        id=source_id,
        path=Path("/nonexistent/in-memory.txt"),
        sha256="0" * 64,
        format=SourceFormat.TEXT,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        extractor="test",
        extractor_version="test/1",
        text=text,
        locator_regions=[LocatorRegion(start=s, end=e, locator=loc) for s, e, loc in spec],
    )
