"""Catch rate and false-positive rate for a critic on one corpus split.

Counts, not just rates: n is small (≈12 defects, ≈10 clean candidates per
split), so a published number must carry its n. Catch is measured twice —
"something fired on the defect file" (what S2's gate asserts) and "the check
the defect was seeded for fired" (a stricter reading).
"""

from __future__ import annotations

from typing import Any

from probative.critics.llm_judge import LLMCritic
from tests.critics._candidates import load_fixture
from tests.critics._corpus import SPLITS, Corpus


def measure(
    corpus: Corpus, split: str, critic: LLMCritic, *, detail: bool = False
) -> dict[str, Any]:
    seeded: list[dict[str, Any]] = []
    for path in corpus.files("seeded", split):
        data = load_fixture(path)
        before = critic.stats.cannot_tell
        findings = critic.check(corpus.parse(path))
        row: dict[str, Any] = {
            "file": path.name,
            "check": data["check"],
            "caught": bool(findings),
            "caught_intended": any(f.check_id == data["check"] for f in findings),
            "fired": sorted({f.check_id for f in findings}),
        }
        if detail:
            row["cannot_tell"] = critic.stats.cannot_tell - before
        seeded.append(row)
    clean: list[dict[str, Any]] = []
    for path in corpus.files("clean", split):
        candidates = corpus.parse(path)
        before = critic.stats.cannot_tell
        findings = critic.check(candidates)
        clean_row: dict[str, Any] = {
            "file": path.name,
            "candidates": len(candidates),
            "flagged_candidates": len({f.target_id for f in findings}),
            "fired": sorted({f.check_id for f in findings}),
        }
        if detail:
            clean_row["cannot_tell"] = critic.stats.cannot_tell - before
        clean.append(clean_row)
    per_check: dict[str, dict[str, int]] = {}
    for row in seeded:
        cell = per_check.setdefault(row["check"], {"n": 0, "caught_intended": 0})
        cell["n"] += 1
        cell["caught_intended"] += int(row["caught_intended"])
    return {
        "critic": critic.rubric.id,
        "split": split,
        "seeded": {
            "n": len(seeded),
            "caught": sum(r["caught"] for r in seeded),
            "caught_intended": sum(r["caught_intended"] for r in seeded),
            "per_check": per_check,
            "files": seeded,
        },
        "clean": {
            "candidates": sum(r["candidates"] for r in clean),
            "flagged_candidates": sum(r["flagged_candidates"] for r in clean),
            "files": clean,
        },
        "judge_stats": _stats(critic),
    }


def _stats(critic: LLMCritic) -> dict[str, Any]:
    stats = critic.stats
    return {
        "calls": stats.calls,
        "usage": stats.usage.model_dump(),
        "met": stats.met,
        "not_met": stats.not_met,
        "cannot_tell": stats.cannot_tell,
        "missing": stats.missing,
        "duplicates": stats.duplicates,
        "unknown_ids": stats.unknown_ids,
        "unresolved_quotes": stats.unresolved_quotes,
    }


def measure_stress(corpus: Corpus, critic: LLMCritic) -> dict[str, Any]:
    """Hard cases: for each file, did exactly the expected set of checks fire?
    Reported, never gating, never tuned on."""
    rows: list[dict[str, Any]] = []
    for path in corpus.stress_files():
        data = load_fixture(path)
        fired = sorted({f.check_id for f in critic.check(corpus.parse(path))})
        expected = sorted(data["expect_fired"])
        allowed = sorted(data.get("allow_also", []))
        rows.append(
            {
                "file": path.name,
                "expect_fired": expected,
                "allow_also": allowed,
                # every expected check fired, and nothing outside expected + tolerated did
                "fired": fired,
                "as_expected": set(expected) <= set(fired) <= set(expected) | set(allowed),
                "why": data["why"],
            }
        )
    return {
        "critic": critic.rubric.id,
        "n": len(rows),
        "as_expected": sum(r["as_expected"] for r in rows),
        "files": rows,
        "judge_stats": _stats(critic),
    }


def measure_mixed(corpus: Corpus, critic: LLMCritic) -> dict[str, Any]:
    """The production condition the per-file split runs do not exercise: seeded
    and clean candidates from every split interleaved and judged together, in
    the critic's own batch size. Candidate ids are made unique across splits
    (dev and held-out defect files share file stems)."""
    seeded: list[Any] = []
    clean: list[Any] = []
    intended: dict[str, str] = {}
    for split in SPLITS:
        for path in corpus.files("seeded", split):
            data = load_fixture(path)
            (cand,) = corpus.build_from(data, source_id=f"src_{split}_{path.stem}")
            seeded.append(cand)
            intended[cand.id] = data["check"]  # type: ignore[attr-defined]
        for path in corpus.files("clean", split):
            data = load_fixture(path)
            clean.extend(corpus.build_from(data, source_id=f"src_{split}_{path.stem}"))
    interleaved: list[Any] = []
    for i in range(max(len(seeded), len(clean))):
        interleaved.extend(seeded[i : i + 1])
        interleaved.extend(clean[i : i + 1])
    findings = critic.check(interleaved)
    clean_ids = {c.id for c in clean}  # type: ignore[attr-defined]
    by_target: dict[str, set[str]] = {}
    for finding in findings:
        by_target.setdefault(str(finding.target_id), set()).add(finding.check_id)
    return {
        "critic": critic.rubric.id,
        "candidates": len(interleaved),
        "seeded": {
            "n": len(seeded),
            "caught": sum(c.id in by_target for c in seeded),  # type: ignore[attr-defined]
            "caught_intended": sum(
                intended[c.id] in by_target.get(c.id, set())  # type: ignore[attr-defined]
                for c in seeded
            ),
        },
        "clean": {
            "candidates": len(clean),
            "flagged_candidates": sum(cid in by_target for cid in clean_ids),
        },
        "judge_stats": _stats(critic),
    }
