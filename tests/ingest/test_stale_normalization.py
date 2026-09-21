"""reextract() must detect when a source's recorded normalisation version
no longer matches what current code would produce — those offsets are not
guaranteed valid any more."""

from __future__ import annotations

import pytest

from probative.core.evidence import EvidenceKind, StaleNormalizationError, Tier
from probative.ingest import ingest, reextract, spans
from tests.ingest._paths import FIXTURES


def test_reextract_rejects_a_stale_normalization_version() -> None:
    source = ingest(FIXTURES / "plain.txt", tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    (span,) = spans(source, [(0, 5)])
    stale = source.model_copy(update={"extractor_version": "text/0-does-not-exist"})

    with pytest.raises(StaleNormalizationError):
        reextract(stale, span)
