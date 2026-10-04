"""Records the reference model's judgements on PB5 corpora and measures both
critics. Never runs in default CI (`-m live`). A developer action:

    ANTHROPIC_API_KEY=sk-... PB5_SPLIT=dev uv run pytest -m live \\
        tests/critics/test_pb5_live_record.py -s

`PB5_SPLIT` is one of:
- `dev`: what prompts are tuned against; re-run freely.
- `held_out`: run once after the prompts are frozen. Already-recorded held-out
  is never overwritten without `PB5_RERECORD_HELD_OUT=1`, which you should only
  set knowing it demotes held-out to dev (OI17 discipline).
- `stress`: hard cases (reported, never gating, never tuned on) and the
  mixed-batch run, which judges every split's candidates interleaved in the
  critic's production batch size.

Always uses REFERENCE_MODEL (OI2): published numbers are not env-overridable.
Both corpora are measured into staging directories and swapped in together only
once everything succeeded (the old directory is kept aside until its replacement
is in place), so a failure mid-run cannot destroy a good recording.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from probative.config import REFERENCE_MODEL
from probative.critics.invest import INVESTCritic
from probative.critics.llm_judge import LLMCritic
from probative.critics.space_warden import SpaceWarden
from probative.llm import LiteLLMProvider
from tests._recording import Recorder
from tests.critics._corpus import INVEST, SPACE_WARDEN, SPLITS, Corpus
from tests.critics._measure import measure, measure_mixed, measure_stress
from tests.critics._replay import recording_dir
from tests.critics._swap import swap_in

pytestmark = pytest.mark.live


def _print_split(name: str, split: str, result: dict[str, Any]) -> None:
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
    print(f"   judge stats: {result['judge_stats']}")


def _print_stress(name: str, stress: dict[str, Any], mixed: dict[str, Any]) -> None:
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


def _stage(staging: Path, result: dict[str, Any]) -> None:
    (staging / "results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def test_record_split_and_measure() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    split = os.environ.get("PB5_SPLIT", "dev")
    assert split in (*SPLITS, "stress"), f"PB5_SPLIT must be one of {(*SPLITS, 'stress')}"

    corpora: tuple[tuple[Corpus, type[LLMCritic]], ...] = (
        (SPACE_WARDEN, SpaceWarden),
        (INVEST, INVESTCritic),
    )
    # Guard every corpus before the first API call, so a refusal wastes nothing.
    for corpus, _ in corpora:
        directory = recording_dir(corpus.name, split)
        already = split == "held_out" and any(directory.glob("*.json"))
        if already and not os.environ.get("PB5_RERECORD_HELD_OUT"):
            pytest.fail(
                f"{directory} already holds held-out recordings; refusing to overwrite. "
                "Set PB5_RERECORD_HELD_OUT=1 only if you accept that this demotes "
                "held_out to dev."
            )

    real = LiteLLMProvider()._completion()  # this module may not import litellm (TID251)
    staged: list[tuple[Path, Path]] = []
    reports: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []
    for corpus, critic_cls in corpora:
        directory = recording_dir(corpus.name, split)
        staging = directory.with_name(f"{split}.recording")
        shutil.rmtree(staging, ignore_errors=True)
        provider = LiteLLMProvider(completion_fn=Recorder(real, staging))

        def new_critic(provider: LiteLLMProvider = provider, cls: Any = critic_cls) -> LLMCritic:
            critic: LLMCritic = cls.from_builtin_rubric(provider, model=REFERENCE_MODEL)
            return critic

        if split == "stress":
            stress = measure_stress(corpus, new_critic())
            mixed = measure_mixed(corpus, new_critic())
            _stage(
                staging,
                {"model": REFERENCE_MODEL, "critic": corpus.name, "stress": stress, "mixed": mixed},
            )
            reports.append((corpus.name, stress, mixed))
        else:
            result = {"model": REFERENCE_MODEL, **measure(corpus, split, new_critic())}
            _stage(staging, result)
            reports.append((corpus.name, result, None))
        staged.append((staging, directory))

    # Only once every corpus has been measured and staged does anything real change.
    swap_in(staged)
    for name, first, second in reports:
        if second is None:
            _print_split(name, split, first)
        else:
            _print_stress(name, first, second)
