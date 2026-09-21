"""Ingesting the same file twice must produce identical source hash and
identical offsets. `ingested_at` (wall-clock) is the one field allowed to
differ."""

from __future__ import annotations

import pytest

from probative.core.evidence import EvidenceKind, Tier
from probative.ingest import ingest
from tests.ingest._paths import FIXTURES, HAPPY_PATH_FIXTURES


@pytest.mark.parametrize("name", HAPPY_PATH_FIXTURES)
def test_reingesting_is_idempotent(name: str) -> None:
    first = ingest(FIXTURES / name, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    second = ingest(FIXTURES / name, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)

    assert first.id == second.id
    assert first.sha256 == second.sha256
    assert first.text == second.text
    assert first.locator_regions == second.locator_regions
    assert first.extractor_version == second.extractor_version
