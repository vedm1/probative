from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ingest"
GOLDEN = FIXTURES / "golden"

HAPPY_PATH_FIXTURES = [
    "plain.txt",
    "crlf.txt",
    "notes.md",
    "data.csv",
    "sheet.xlsx",
    "report.docx",
    "memo.pdf",
]
