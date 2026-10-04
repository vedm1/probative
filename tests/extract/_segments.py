"""Corpus for the PB6-p2 segment pass: one document with four segments and the
traps around them, plus PB4's candidate-free memo (a segment pass on it must
yield nothing). Recorded separately from PB4's corpus so re-recording one never
wipes the other."""

from __future__ import annotations

from tests.extract._helpers import FIXTURES

SEGMENT_RECORDINGS = FIXTURES / "recordings_segments"
SEGMENT_RERECORD_HINT = (
    "Re-record with `ANTHROPIC_API_KEY=... uv run pytest -m live "
    "tests/extract/test_live_record_segments.py -s`"
)
# (document, gold labels). `prd_payments.md` is PB4's messier PRD: its gold file holds no
# segment labels because it never defines a target group ("Shoppers need ..." is a need,
# "As a ..." a story), so every segment predicted on it is a false positive by construction.
SEGMENT_CORPUS = [
    ("prd_segments.md", "prd_segments.json"),
    ("prd_payments.md", "prd_payments_md.json"),
    ("memo_logistics.txt", "memo_logistics.json"),
]
