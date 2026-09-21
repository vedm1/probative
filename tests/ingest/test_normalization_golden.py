"""Pins the normalised text projection of each fixture. A change to
normalisation must fail this test loudly rather than silently invalidating
every offset downstream."""

from __future__ import annotations

import pytest

from probative.core.evidence import EvidenceKind, Tier
from probative.ingest import ingest
from tests.ingest._paths import FIXTURES, GOLDEN, HAPPY_PATH_FIXTURES


@pytest.mark.parametrize("name", HAPPY_PATH_FIXTURES)
def test_normalized_text_matches_golden(name: str) -> None:
    source = ingest(FIXTURES / name, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    golden = (GOLDEN / f"{name}.txt").read_text(encoding="utf-8")
    assert source.text == golden
