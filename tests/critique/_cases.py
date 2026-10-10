"""The recorded end-to-end cases for `probative critique` (PB9).

One recordings directory per case, holding every model response of a full run
(extraction and critics) plus `results.json`: what the run produced when it was
recorded, including its wall-clock time. Recording is a developer action (S3).
"""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
RECORDINGS = FIXTURES / "critique" / "recordings"
CASE_NAMES = ("payments", "folder", "long", "long_dense", "long_b5j16", "long_j32")
# Cases recorded at a non-default concurrency (an experiment, not the default settings).
CASE_OPTIONS: dict[str, dict[str, int]] = {
    "long_b5j16": {"jobs": 16, "batch_size": 5},
    "long_j32": {"jobs": 32, "batch_size": 5},
}


def rerecord_hint(case: str) -> str:
    return (
        f"Re-record with `ANTHROPIC_API_KEY=... PB9_CASE={case} uv run pytest -m live "
        "tests/critique/test_live_record.py -s`"
    )


def case_path(case: str, workdir: Path) -> Path:
    """The path a case points `probative critique` at."""
    if case == "payments":
        return FIXTURES / "extract" / "prd_payments.md"
    if case in ("long", "long_b5j16", "long_j32"):
        return FIXTURES / "critique" / "spec_long.pdf"
    if case == "long_dense":
        return FIXTURES / "critique" / "spec_long_dense.pdf"
    if case == "folder":
        folder = workdir / "specs"
        folder.mkdir(parents=True, exist_ok=True)
        for source, name in (
            (FIXTURES / "extract" / "prd_segments.md", "prd_segments.md"),
            (FIXTURES / "tracker" / "jira_visible.csv", "backlog.csv"),
            (FIXTURES / "confluence" / "page_export.doc", "page_export.doc"),
        ):
            shutil.copy(source, folder / name)
        return folder
    raise KeyError(case)
