"""The phase's reason to exist: an EvidenceSpan's offsets must survive
re-extraction, byte-identical, for every supported format."""

from __future__ import annotations

import pytest

from probative.core.evidence import EvidenceKind, Tier
from probative.ingest import ingest, reextract, spans
from tests.ingest._paths import FIXTURES, HAPPY_PATH_FIXTURES


@pytest.mark.parametrize("name", HAPPY_PATH_FIXTURES)
def test_roundtrip_survives_reextraction(name: str) -> None:
    source = ingest(FIXTURES / name, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    text_len = len(source.text)

    ranges = [(0, min(5, text_len))]
    if text_len > 10:
        ranges.append((text_len - 5, text_len))
    mid = text_len // 2
    if 0 < mid < text_len - 1:
        ranges.append((mid, min(mid + 3, text_len)))

    for span in spans(source, ranges):
        assert reextract(source, span) == span.text
