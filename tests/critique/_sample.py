"""A deterministic report for renderer tests, built through the real pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

from probative.critique.pipeline import CritiqueOptions, run_critique
from probative.critique.report import CritiqueReport
from probative.critique.sources import LoadedSource
from tests.critique._builders import make_source
from tests.critique._scripted import Scripted

HOSTILE = (
    "NEED: Users need a FLAG <script>alert(1)</script> | `tick` **bold** [x](http://evil.test)"
)
DOC = f"""# Checkout PRD

CLAIM: Conversion drops 12% at the payment step.
CLAIM: FLAG Competitors convert far better than we do.
{HOSTILE}
NEED: Users want to pay without retyping details.
STORY: As a shopper I want to save my card so that I can pay faster.
SEGMENT: Adults aged 25 to 45 who shop online.
FORECAST: Launching this will double repeat purchases.
"""


def sample_report(text: str = DOC, name: str = "checkout-prd.md") -> CritiqueReport:
    src = make_source(text, name=name)
    return run_critique(
        name,
        [LoadedSource(src, "detected")],
        [],
        Scripted(),
        CritiqueOptions(
            model="test/model",
            jobs=1,
            now=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            clock=lambda: 0.0,
            tool_version="0.0.0-test",
        ),
    )
