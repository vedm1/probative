from __future__ import annotations

import json
from pathlib import Path

from probative.core.critic import Finding, Severity
from probative.core.graph.validators import Violation
from probative.graph_runtime.patch import Patch, PatchStore
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.runfiles import RunFiles
from tests.graph_runtime._support import good_ratings, result


def test_patch_id_is_content_derived_and_stable() -> None:
    a = Patch.build("agent", Phase.P3, 1, result(list(good_ratings())))
    b = Patch.build("agent", Phase.P3, 2, result(list(good_ratings())))
    assert a.id == b.id and a.id.startswith("patch_")
    c = Patch.build("agent", Phase.P3, 1, result([good_ratings()[0]]))
    assert c.id != a.id


def test_store_round_trips_a_patch(tmp_path: Path) -> None:
    files = RunFiles(tmp_path / "r")
    store = PatchStore(files)
    p = Patch.build("agent", Phase.P3, 1, result(list(good_ratings())))
    store.save(p)
    assert store.load(p.id) == p


def test_rejected_patch_keeps_findings_and_violations(tmp_path: Path) -> None:
    files = RunFiles(tmp_path / "r")
    store = PatchStore(files)
    p = Patch.build("agent", Phase.P3, 2, result(list(good_ratings())))
    f = Finding(
        critic_id="c", check_id="k", severity=Severity.BLOCK, invariant="I3",
        message="m", remedy="r",
    )  # fmt: skip
    v = Violation("I1", "I1_ORPHAN_CLAIM", "claim_000000000000", "no evidence")
    path = store.save_rejected(p, [f], [v])
    assert path.parent == files.rejected_dir and "c2" in path.name
    doc = json.loads(path.read_text())
    assert doc["findings"][0]["check_id"] == "k"
    assert doc["violations"][0]["code"] == "I1_ORPHAN_CLAIM"


def test_run_files_paths_live_under_the_run_directory(tmp_path: Path) -> None:
    files = RunFiles(tmp_path / "r")
    for path in (
        files.graph_path,
        files.mirror_path,
        files.ledger_path,
        files.checkpoint_path,
        files.interactions_path,
    ):
        assert path.parent == files.root
    assert files.checkpoint_path.name == "checkpoint.sqlite"
