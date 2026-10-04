"""Printing and staging helpers shared by the live-recording tests (PB5, PB6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def print_split(name: str, split: str, result: dict[str, Any]) -> None:
    seeded, clean = result["seeded"], result["clean"]
    print(f"\n== {name} [{split}]")
    print(
        f"   caught {seeded['caught']}/{seeded['n']} "
        f"(intended check {seeded['caught_intended']}/{seeded['n']}); "
        f"false positives {clean['flagged_candidates']}/{clean['candidates']}"
    )
    print(f"   per check: {seeded['per_check']}")
    rows = seeded["files"]
    print(f"   missed: {[r['file'] for r in rows if not r['caught']]}")
    wrong = [r["file"] for r in rows if r["caught"] and not r["caught_intended"]]
    print(f"   wrong-check: {wrong}")
    flagged = [(r["file"], r["fired"]) for r in clean["files"] if r["flagged_candidates"]]
    print(f"   flagged clean: {flagged}")
    silent = [r["file"] for r in rows if r.get("cannot_tell")]
    if any("cannot_tell" in r for r in rows):
        print(f"   SILENT-PASS (cannot_tell on a seeded defect): {silent}")
    print(f"   judge stats: {result['judge_stats']}")


def print_stress(name: str, stress: dict[str, Any], mixed: dict[str, Any]) -> None:
    print(f"\n== {name} [stress]")
    print(f"   hard cases as expected: {stress['as_expected']}/{stress['n']}")
    for row in stress["files"]:
        if not row["as_expected"]:
            print(
                f"   UNEXPECTED {row['file']}: expected {row['expect_fired']}, fired {row['fired']}"
            )
            print(f"      why the label: {row['why']}")
    print(f"   stress judge stats: {stress['judge_stats']}")
    seeded, clean = mixed["seeded"], mixed["clean"]
    print(
        f"   MIXED batches ({mixed['judge_stats']['calls']} calls over {mixed['candidates']} "
        f"candidates): caught {seeded['caught']}/{seeded['n']} "
        f"(intended {seeded['caught_intended']}/{seeded['n']}); "
        f"false positives {clean['flagged_candidates']}/{clean['candidates']}"
    )
    print(f"   mixed judge stats: {mixed['judge_stats']}")


def stage(staging: Path, result: dict[str, Any]) -> None:
    (staging / "results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
