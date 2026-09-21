"""A few narrow edge cases that don't belong in the committed round-trip
corpus: blank lines in a CSV, invalid UTF-8, and a file that merely isn't a
valid zip container for the two Office formats (the same signature a
password-protected file produces — see xlsx.py/docx_.py)."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from probative.core.evidence import EmptySourceError, EncryptedSourceError, EvidenceKind, Tier
from probative.ingest import ingest


def test_csv_tolerates_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "with_blanks.csv"
    path.write_text("a,b\n1,2\n\n3,4\n", encoding="utf-8")
    source = ingest(path, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
    assert source.text == "a,b\n1,2\n\n3,4\n"


def test_txt_rejects_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "bad_encoding.txt"
    path.write_bytes(b"\xff\xfe not valid utf-8")
    with pytest.raises(Exception, match="not valid UTF-8"):
        ingest(path, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)


def test_xlsx_rejects_a_file_that_is_not_a_valid_zip(tmp_path: Path) -> None:
    path = tmp_path / "garbage.xlsx"
    path.write_bytes(b"not a zip file at all")
    with pytest.raises(EncryptedSourceError):
        ingest(path, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)


def test_docx_rejects_a_file_that_is_not_a_valid_zip(tmp_path: Path) -> None:
    path = tmp_path / "garbage.docx"
    path.write_bytes(b"not a zip file at all")
    with pytest.raises(EncryptedSourceError):
        ingest(path, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)


def test_xlsx_with_every_sheet_empty_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "blank.xlsx"
    openpyxl.Workbook().save(path)
    with pytest.raises(EmptySourceError):
        ingest(path, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY)
