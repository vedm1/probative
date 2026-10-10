"""Records a full `probative critique` run for one case and measures it. Never
runs in default CI (`-m live`). A developer action, one case at a time:

    ANTHROPIC_API_KEY=sk-... PB9_CASE=payments uv run pytest -m live \\
        tests/critique/test_live_record.py -s

`PB9_CASE` is required (payments | folder | long). It replaces that case's
directory under tests/fixtures/critique/recordings/ and rewrites `results.json`,
which the replay tests pin. The `long` case is the gating check: its wall-clock
time is the number the 60-second gate is judged on.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from probative.config import REFERENCE_MODEL
from probative.critique import CritiqueOptions, critique
from probative.llm import LiteLLMProvider
from tests._recording import Recorder
from tests.critique._cases import CASE_NAMES, CASE_OPTIONS, RECORDINGS, case_path

pytestmark = pytest.mark.live


def _options(case: str) -> dict[str, int]:
    return CASE_OPTIONS.get(case, {})


def test_record_case_and_measure(tmp_path: Path) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    case = os.environ.get("PB9_CASE", "")
    if case not in CASE_NAMES:
        pytest.fail(f"set PB9_CASE to one of {', '.join(CASE_NAMES)}")

    real = LiteLLMProvider(num_retries=3, timeout=120.0)._completion()
    target = RECORDINGS / case
    staging = RECORDINGS / f"{case}.recording"
    shutil.rmtree(staging, ignore_errors=True)
    provider = LiteLLMProvider(completion_fn=Recorder(real, staging), num_retries=3)

    started = time.monotonic()
    options = CritiqueOptions(model=REFERENCE_MODEL, **_options(case))
    run = critique(case_path(case, tmp_path), provider, options)
    wall = time.monotonic() - started
    report = run.report

    results = {
        "model": REFERENCE_MODEL,
        "case": case,
        "wall_seconds": round(wall, 1),
        "calls": report.run.calls,
        "input_tokens": report.run.input_tokens,
        "output_tokens": report.run.output_tokens,
        "jobs": report.run.jobs,
        "reply": report.run.reply,
        "batch_size": options.batch_size,
        "window_chars": options.window_chars,
        "documents": [
            {"file": d.file_name, "chars": d.chars, "pages": d.pages, "candidates": d.candidates}
            for d in report.documents
        ],
        "incomplete": report.incomplete,
        "totals": report.totals.model_dump(),
        "dimensions": {
            d.critic_id: {
                "status": d.status.value,
                "checked": d.checked,
                "flagged": d.flagged,
                "counts": d.counts.model_dump(),
            }
            for d in report.dimensions
        },
    }
    (staging / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)
    print(f"\n== {case}: {wall:.1f}s, {report.run.calls} calls, totals {report.totals}")
    for d in report.dimensions:
        print(f"   {d.label}: {d.status.value} checked={d.checked} flagged={d.flagged}")
