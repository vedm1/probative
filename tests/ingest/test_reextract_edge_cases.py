"""reextract()'s two other failure paths, beyond staleness: a span from a
different source, and a source whose file changed on disk after ingestion."""

from __future__ import annotations

from pathlib import Path

import pytest

from probative.core.evidence import CorruptSourceError, EvidenceKind, Tier
from probative.ingest import ingest, reextract, spans
from tests.ingest._paths import FIXTURES


def test_reextract_rejects_a_span_from_a_different_source(tmp_path: Path) -> None:
    plain = ingest(FIXTURES / "plain.txt", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    other_path = tmp_path / "other.txt"
    other_path.write_text("A completely different file.\n", encoding="utf-8")
    other = ingest(other_path, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    (span_from_other,) = spans(other, [(0, 5)])

    with pytest.raises(ValueError):
        reextract(plain, span_from_other)


def test_reextract_detects_file_changed_on_disk(tmp_path: Path) -> None:
    path = tmp_path / "mutable.txt"
    path.write_text("Original content.\n", encoding="utf-8")
    source = ingest(path, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    (span,) = spans(source, [(0, 8)])

    path.write_text("Different content now.\n", encoding="utf-8")

    with pytest.raises(CorruptSourceError):
        reextract(source, span)
