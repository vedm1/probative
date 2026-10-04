"""Records the reference model's judgements on the PB7 corpora and measures the
critics. Never runs in default CI (`-m live`). A developer action, in this order,
once per critic:

    ANTHROPIC_API_KEY=sk-... PB7C_SPLIT=dev uv run pytest -m live \\
        tests/critics/test_pb7_live_record.py -k constraint -s
    ANTHROPIC_API_KEY=sk-... PB7D_SPLIT=dev uv run pytest -m live \\
        tests/critics/test_pb7_live_record.py -k dependency -s

`PB7C_SPLIT` (ConstraintCritic) and `PB7D_SPLIT` (DependencyCritic) are required,
with no default (a mistyped name once silently re-recorded dev in PB6), and are one of:
- `dev`: what the prompts are tuned against; re-run freely.
- `held_out`: run ONCE, after the prompts are frozen. Already-recorded held-out is
  never overwritten without `PB7C_RERECORD_HELD_OUT=1` / `PB7D_RERECORD_HELD_OUT=1`,
  which you should set only knowing it demotes held-out to dev (OI17 discipline).
- `stress`: hard cases (reported, never gating, never tuned on). DependencyCritic's
  stress run also records the mixed-batch measurement (every split's candidates
  interleaved at the production batch size); ConstraintCritic has no mixed run,
  because its unit is a document, and batching is exercised by the 8-constraint
  stress document.

Always uses REFERENCE_MODEL (OI2). A recording is measured into a staging directory
and swapped in only once it succeeded (`_swap.swap_in`).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from typing import Any

import pytest

from probative.config import REFERENCE_MODEL
from probative.critics.constraint_critic import ConstraintCritic
from probative.critics.dependency_critic import DependencyCritic
from probative.llm import LiteLLMProvider
from tests._recording import Recorder
from tests.critics._corpus import DEPENDENCY_CRITIC, SPLITS
from tests.critics._measure import measure, measure_mixed, measure_stress
from tests.critics._replay import recording_dir
from tests.critics._report import print_split, print_stress, stage
from tests.critics._swap import swap_in
from tests.critics._trace_corpus import CONSTRAINT_CRITIC
from tests.critics._trace_measure import measure_trace, measure_trace_stress

pytestmark = pytest.mark.live


def _prepare(prefix: str, name: str) -> tuple[str, Any, Any, Callable[[], LiteLLMProvider]]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    variable = f"{prefix}_SPLIT"
    split = os.environ.get(variable)
    assert split, f"{variable} must be set explicitly (a mistyped name must not re-record dev)"
    assert split in (*SPLITS, "stress"), f"{variable} must be one of {(*SPLITS, 'stress')}"

    directory = recording_dir(name, split)
    already = split == "held_out" and any(directory.glob("*.json"))
    if already and not os.environ.get(f"{prefix}_RERECORD_HELD_OUT"):
        pytest.fail(
            f"{directory} already holds held-out recordings; refusing to overwrite. "
            f"Set {prefix}_RERECORD_HELD_OUT=1 only if you accept that this demotes "
            "held_out to dev."
        )
    real = LiteLLMProvider()._completion()  # this module may not import litellm (TID251)
    staging = directory.with_name(f"{split}.recording")
    shutil.rmtree(staging, ignore_errors=True)
    return split, directory, staging, lambda: LiteLLMProvider(completion_fn=Recorder(real, staging))


def test_record_constraint_critic_and_measure() -> None:
    split, directory, staging, provider = _prepare("PB7C", CONSTRAINT_CRITIC.name)

    def new_critic() -> ConstraintCritic:
        return ConstraintCritic.from_builtin_rubric(provider(), model=REFERENCE_MODEL)

    if split == "stress":
        stress = measure_trace_stress(CONSTRAINT_CRITIC, new_critic())
        stage(
            staging,
            {"model": REFERENCE_MODEL, "critic": CONSTRAINT_CRITIC.name, "stress": stress},
        )
        swap_in([(staging, directory)])
        print(f"\n== {CONSTRAINT_CRITIC.name} [stress]: {stress['as_expected']}/{stress['n']}")
        for row in stress["files"]:
            if not row["as_expected"]:
                print(f"   UNEXPECTED {row['file']}: flagged {row['flagged']} ({row['why']})")
        print(f"   judge stats: {stress['judge_stats']}")
    else:
        result = {
            "model": REFERENCE_MODEL,
            **measure_trace(CONSTRAINT_CRITIC, split, new_critic()),
        }
        stage(staging, result)
        swap_in([(staging, directory)])
        seeded, clean = result["seeded"], result["clean"]
        print(f"\n== {CONSTRAINT_CRITIC.name} [{split}]")
        print(
            f"   untraced constraints caught {seeded['caught']}/{seeded['untraced_constraints']}; "
            f"documents caught in full {seeded['documents_caught_all']}/{seeded['documents']}; "
            f"traced constraints flagged in seeded documents "
            f"{seeded['flagged_traced']}/{seeded['traced_constraints']}"
        )
        print(
            f"   clean: flagged {clean['flagged_constraints']}/{clean['constraints']} "
            f"constraints over {clean['documents']} documents"
        )
        print(f"   judge stats: {result['judge_stats']}")


def test_record_dependency_critic_and_measure() -> None:
    split, directory, staging, provider = _prepare("PB7D", DEPENDENCY_CRITIC.name)
    corpus = DEPENDENCY_CRITIC

    def new_critic() -> DependencyCritic:
        return DependencyCritic.from_builtin_rubric(provider(), model=REFERENCE_MODEL)

    if split == "stress":
        stress = measure_stress(corpus, new_critic())
        mixed = measure_mixed(corpus, new_critic())
        stage(
            staging,
            {"model": REFERENCE_MODEL, "critic": corpus.name, "stress": stress, "mixed": mixed},
        )
        swap_in([(staging, directory)])
        print_stress(corpus.name, stress, mixed)
    else:
        result = {"model": REFERENCE_MODEL, **measure(corpus, split, new_critic(), detail=True)}
        stage(staging, result)
        swap_in([(staging, directory)])
        print_split(corpus.name, split, result)
