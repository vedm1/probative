"""Calibration of the flagged reply mode (PB9 lever B).

The PB5-PB8 numbers describe the `full` reply (a verdict for every candidate and
check). The flagged reply is a different prompt and a different contract, so it is
measured on its own, with the same discipline: dev first (the only split a flagged
prompt may be tuned on), held-out once, stress and mixed reported and never tuned on.
Recordings live apart from the full-mode ones.

The acceptance rule is fixed here, before any flagged recording exists, so it cannot
be tuned to the result. Flagged replies are acceptable for `probative critique` iff,
for EVERY LLM critic on its held-out split,
  caught_flagged >= caught_full - 1   and
  false_positives_flagged <= false_positives_full + 1
(counts of seeded defects caught and of clean candidates flagged), and no seeded
defect was passed by a `cannot_tell` (a defect that was NOT caught and drew one).
Otherwise `critique` keeps `full` replies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from probative.config import REFERENCE_MODEL
from probative.critics.dependency_critic import DependencyCritic
from probative.critics.evidence_auditor import EvidenceAuditor
from probative.critics.invest import INVESTCritic
from probative.critics.llm_judge import LLMCritic
from probative.critics.red_team import RedTeam
from probative.critics.segment_skeptic import SegmentSkeptic
from probative.critics.space_warden import SpaceWarden
from probative.llm import Provider
from tests.critics._corpus import (
    DEPENDENCY_CRITIC,
    EVIDENCE_AUDITOR,
    INVEST,
    RED_TEAM,
    SEGMENT_SKEPTIC,
    SPACE_WARDEN,
    Corpus,
)
from tests.critics._paths import FIXTURES

FLAGGED_RECORDINGS = FIXTURES / "recordings_flagged"
FULL_RECORDINGS = FIXTURES / "recordings"
SPLITS_ALL = ("dev", "held_out", "stress")
CRITICS: dict[str, tuple[Corpus, type[LLMCritic]]] = {
    "space_warden": (SPACE_WARDEN, SpaceWarden),
    "invest": (INVEST, INVESTCritic),
    "evidence_auditor": (EVIDENCE_AUDITOR, EvidenceAuditor),
    "segment_skeptic": (SEGMENT_SKEPTIC, SegmentSkeptic),
    "dependency_critic": (DEPENDENCY_CRITIC, DependencyCritic),
    "red_team": (RED_TEAM, RedTeam),
}
HINT = (
    "Record with `ANTHROPIC_API_KEY=... FLAGGED_CRITIC=<name|all> "
    "FLAGGED_SPLIT=<dev|held_out|stress> uv run pytest -m live "
    "tests/critics/test_flagged_live_record.py -s` (dev first; held-out once, after the "
    "flagged prompt is frozen)."
)


def flagged_dir(critic: str, split: str) -> Path:
    return FLAGGED_RECORDINGS / critic / split


def new_flagged_critic(name: str, provider: Provider) -> LLMCritic:
    _, cls = CRITICS[name]
    return cls.from_builtin_rubric(provider, model=REFERENCE_MODEL, reply="flagged")  # type: ignore[attr-defined,no-any-return]


def load_results(directory: Path) -> dict[str, Any] | None:
    path = directory / "results.json"
    if not path.exists():
        return None
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def acceptable(full: dict[str, Any], flagged: dict[str, Any]) -> tuple[bool, str]:
    """The pre-registered rule, on one critic's held-out results."""
    caught_full, caught_flagged = full["seeded"]["caught"], flagged["seeded"]["caught"]
    fp_full, fp_flagged = (
        full["clean"]["flagged_candidates"],
        flagged["clean"]["flagged_candidates"],
    )
    silent = [
        r["file"] for r in flagged["seeded"]["files"] if not r["caught"] and r.get("cannot_tell")
    ]
    ok = caught_flagged >= caught_full - 1 and fp_flagged <= fp_full + 1 and not silent
    detail = (
        f"caught {caught_flagged} vs {caught_full} full; false positives {fp_flagged} vs "
        f"{fp_full} full; silent cannot_tell on {silent}"
    )
    return ok, detail
