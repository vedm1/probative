from __future__ import annotations

import shutil
from pathlib import Path

from probative.core.evidence import EvidenceKind, Tier
from probative.ingest import ingest
from tests.critique._cases import FIXTURES, case_path


def _ingest(name: str):  # type: ignore[no-untyped-def]
    return ingest(FIXTURES / "critique" / name, tier=Tier.T4, kind=EvidenceKind.DOCUMENTARY)


def test_spec_long_is_a_thirty_page_pdf_of_about_ninety_thousand_characters() -> None:
    source = _ingest("spec_long.pdf")
    pages = {r.locator.page for r in source.locator_regions}
    assert max(p for p in pages if p is not None) == 30
    assert 80_000 <= len(source.text) <= 95_000


def test_spec_long_dense_is_the_claim_dense_stress_case() -> None:
    source = _ingest("spec_long_dense.pdf")
    pages = {r.locator.page for r in source.locator_regions}
    assert max(p for p in pages if p is not None) == 30
    assert len(source.text) > 85_000


def test_realistic_density_is_the_stated_one() -> None:
    """The gate (G1') is stated against these totals: 90 claims, 27 needs, 6 segments,
    21 stories, 9 constraints, 9 dependencies, 9 forecasts."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pb9_generate", FIXTURES / "critique" / "generate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    counts = module.REALISTIC["counts"]
    totals = [c * module.REALISTIC["parts"] for c in counts]
    assert totals == [90, 27, 6, 21, 9, 9, 9]
    assert sum(module.DENSE["counts"]) * module.DENSE["parts"] > 3 * sum(totals)


def test_folder_case_builds_three_distinct_formats(tmp_path: Path) -> None:
    folder = case_path("folder", tmp_path)
    assert sorted(p.name for p in folder.iterdir()) == [
        "backlog.csv",
        "page_export.doc",
        "prd_segments.md",
    ]
    shutil.rmtree(folder)
