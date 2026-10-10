"""Records the reference model's FLAGGED replies on the existing critic corpora and
measures them. Never runs in default CI (`-m live`). A developer action, in this order:

    ANTHROPIC_API_KEY=sk-... FLAGGED_CRITIC=all FLAGGED_SPLIT=dev uv run pytest -m live \\
        tests/critics/test_flagged_live_record.py -s

`FLAGGED_CRITIC` is a critic name or `all`. `FLAGGED_SPLIT`:
- `dev`: the only split the flagged prompt may be tuned on; re-run freely.
- `held_out`: run ONCE, after the flagged prompt is frozen. Never overwritten without
  `FLAGGED_RERECORD_HELD_OUT=1`, which demotes it to dev (OI17 discipline).
- `stress`: hard cases and the mixed-batch run (reported, never tuned on).

The acceptance rule is in tests/critics/_flagged.py and was fixed before any recording.
"""

from __future__ import annotations

import os
import shutil

import pytest

from probative.config import REFERENCE_MODEL
from probative.llm import LiteLLMProvider
from tests._recording import Recorder
from tests.critics._flagged import CRITICS, SPLITS_ALL, flagged_dir, new_flagged_critic
from tests.critics._measure import measure, measure_mixed, measure_stress
from tests.critics._report import print_split, print_stress, stage
from tests.critics._swap import swap_in

pytestmark = pytest.mark.live


def test_record_flagged_split_and_measure() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    split = os.environ.get("FLAGGED_SPLIT", "")
    assert split in SPLITS_ALL, f"FLAGGED_SPLIT must be one of {SPLITS_ALL}"
    wanted = os.environ.get("FLAGGED_CRITIC", "")
    names = list(CRITICS) if wanted == "all" else [wanted]
    assert all(n in CRITICS for n in names), (
        f"FLAGGED_CRITIC must be 'all' or one of {list(CRITICS)}"
    )

    real = LiteLLMProvider(num_retries=3, timeout=120.0)._completion()
    for name in names:
        corpus, _ = CRITICS[name]
        directory = flagged_dir(name, split)
        already = split == "held_out" and any(directory.glob("*.json"))
        if already and not os.environ.get("FLAGGED_RERECORD_HELD_OUT"):
            pytest.fail(f"{directory} already holds held-out recordings; refusing to overwrite")
        staging = directory.with_name(f"{split}.recording")
        shutil.rmtree(staging, ignore_errors=True)
        provider = LiteLLMProvider(completion_fn=Recorder(real, staging), num_retries=3)

        if split == "stress":
            stress = measure_stress(corpus, new_flagged_critic(name, provider))
            mixed = measure_mixed(corpus, new_flagged_critic(name, provider))
            stage(
                staging,
                {"model": REFERENCE_MODEL, "critic": name, "stress": stress, "mixed": mixed},
            )
            swap_in([(staging, directory)])
            print_stress(name, stress, mixed)
        else:
            result = {
                "model": REFERENCE_MODEL,
                **measure(corpus, split, new_flagged_critic(name, provider), detail=True),
            }
            stage(staging, result)
            swap_in([(staging, directory)])
            print_split(name, split, result)
