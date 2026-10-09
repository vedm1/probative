"""Corpus for the PB8 forecast pass: one document with four forecasts and the
traps around them, plus PB4's memo and PRD (a forecast pass on them is
measured, not assumed empty). Recorded separately from PB4's and PB6-p2's
corpora so re-recording one never wipes the others."""

from __future__ import annotations

from tests.extract._helpers import FIXTURES

FORECAST_RECORDINGS = FIXTURES / "recordings_forecasts"
FORECAST_RERECORD_HINT = (
    "Re-record with `ANTHROPIC_API_KEY=... uv run pytest -m live "
    "tests/extract/test_live_record_forecasts.py -s`"
)
# (document, gold labels). The memo and PB4's PRD carry no forecast labels, so every
# forecast predicted on them is counted as a false positive.
FORECAST_CORPUS = [
    ("prd_forecasts.md", "prd_forecasts.json"),
    ("prd_payments.md", "prd_payments_md.json"),
    ("memo_logistics.txt", "memo_logistics.json"),
]
