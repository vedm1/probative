"""Every named failure mode raises a typed error naming the offending file
— never a silent partial extraction."""

from __future__ import annotations

import pytest

from probative.core.evidence import (
    CorruptSourceError,
    EmptySourceError,
    EncryptedSourceError,
    EvidenceKind,
    MalformedCSVError,
    NoTextLayerError,
    Tier,
    UnsupportedFormatError,
)
from probative.ingest import ingest
from tests.ingest._paths import FIXTURES


def _assert_names_file(exc: Exception, path: object) -> None:
    assert str(path) in str(exc)


@pytest.mark.parametrize(
    ("filename", "exc_type"),
    [
        ("empty.txt", EmptySourceError),
        ("encrypted.pdf", EncryptedSourceError),
        ("corrupt.pdf", CorruptSourceError),
        ("scanned.pdf", NoTextLayerError),
        ("bad_columns.csv", MalformedCSVError),
        ("unsupported.xyz", UnsupportedFormatError),
    ],
)
def test_failure_mode_raises_typed_error_naming_the_file(
    filename: str, exc_type: type[Exception]
) -> None:
    path = FIXTURES / filename
    with pytest.raises(exc_type) as exc_info:
        ingest(path, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    _assert_names_file(exc_info.value, path)
