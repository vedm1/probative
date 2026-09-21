"""spans() must reject an invalid range rather than silently clamping it."""

from __future__ import annotations

import pytest

from probative.core.evidence import EvidenceKind, SpanOutOfRangeError, Tier
from probative.ingest import ingest, spans
from tests.ingest._paths import FIXTURES


def test_start_not_before_end_is_rejected() -> None:
    source = ingest(FIXTURES / "plain.txt", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    with pytest.raises(SpanOutOfRangeError):
        spans(source, [(5, 5)])


def test_end_past_text_length_is_rejected() -> None:
    source = ingest(FIXTURES / "plain.txt", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    with pytest.raises(SpanOutOfRangeError):
        spans(source, [(0, len(source.text) + 1)])
