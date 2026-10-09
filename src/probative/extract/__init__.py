"""Shallow extraction (PROBATIVE_PHASE_SPECS.md, PB4): typed, located
candidates from one `Source`, with no graph.

Public API: `extract_candidates`, `score_extraction`, `gold_candidates`.
"""

from __future__ import annotations

from probative.extract.pipeline import extract_candidates
from probative.extract.prompts import FORECAST_PASS, PASSES, SEGMENT_PASS
from probative.extract.scoring import (
    ExtractionScore,
    GoldLabel,
    GoldLabelError,
    KindScore,
    gold_candidates,
    load_gold_labels,
    score_extraction,
)

__all__ = [
    "FORECAST_PASS",
    "PASSES",
    "SEGMENT_PASS",
    "ExtractionScore",
    "GoldLabel",
    "GoldLabelError",
    "KindScore",
    "extract_candidates",
    "gold_candidates",
    "load_gold_labels",
    "score_extraction",
]
