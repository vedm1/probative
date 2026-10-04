"""Records the reference model's judgements on the PB6-p2 SegmentSkeptic
corpus and measures the critic. Never runs in default CI (`-m live`). A
developer action, in this order:

    ANTHROPIC_API_KEY=sk-... PB6P2_SPLIT=dev uv run pytest -m live \\
        tests/critics/test_pb6p2_live_record.py -s

`PB6P2_SPLIT` is one of:
- `dev`: what the prompt is tuned against; re-run freely.
- `held_out`: run ONCE, after the prompt is frozen. Already-recorded held-out
  is never overwritten without `PB6P2_RERECORD_HELD_OUT=1`, which you should only
  set knowing it demotes held-out to dev (OI17 discipline).
- `stress`: hard cases (reported, never gating, never tuned on) and the
  mixed-batch run, which judges every split's candidates interleaved in the
  production batch size.

Always uses REFERENCE_MODEL (OI2). The recording is measured into a staging
directory and swapped in only once it succeeded (`_swap.swap_in`).
"""

from __future__ import annotations

import os
import shutil

import pytest

from probative.config import REFERENCE_MODEL
from probative.critics.segment_skeptic import SegmentSkeptic
from probative.llm import LiteLLMProvider
from tests._recording import Recorder
from tests.critics._corpus import SEGMENT_SKEPTIC, SPLITS
from tests.critics._measure import measure, measure_mixed, measure_stress
from tests.critics._replay import recording_dir
from tests.critics._report import print_split, print_stress, stage
from tests.critics._swap import swap_in

pytestmark = pytest.mark.live


def test_record_split_and_measure() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    split = os.environ.get("PB6P2_SPLIT")
    assert split, (
        "PB6P2_SPLIT must be set explicitly (a mistyped name must not silently re-record dev)"
    )
    assert split in (*SPLITS, "stress"), f"PB6P2_SPLIT must be one of {(*SPLITS, 'stress')}"

    corpus = SEGMENT_SKEPTIC
    directory = recording_dir(corpus.name, split)
    already = split == "held_out" and any(directory.glob("*.json"))
    if already and not os.environ.get("PB6P2_RERECORD_HELD_OUT"):
        pytest.fail(
            f"{directory} already holds held-out recordings; refusing to overwrite. "
            "Set PB6P2_RERECORD_HELD_OUT=1 only if you accept that this demotes "
            "held_out to dev."
        )

    real = LiteLLMProvider()._completion()  # this module may not import litellm (TID251)
    staging = directory.with_name(f"{split}.recording")
    shutil.rmtree(staging, ignore_errors=True)
    provider = LiteLLMProvider(completion_fn=Recorder(real, staging))

    def new_critic() -> SegmentSkeptic:
        return SegmentSkeptic.from_builtin_rubric(provider, model=REFERENCE_MODEL)

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
