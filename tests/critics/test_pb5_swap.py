"""`swap_in` never loses a good recording: on any failure the old directories
come back. This is the safety net for a developer action that costs real money
to repeat, so it is proven here, key-free."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.critics._swap import swap_in


def _dir(path: Path, name: str, content: str) -> Path:
    path.mkdir(parents=True)
    (path / name).write_text(content)
    return path


def test_swaps_every_pair_and_leaves_no_backup(tmp_path: Path) -> None:
    old_a = _dir(tmp_path / "a" / "dev", "x.json", "old-a")
    old_b = _dir(tmp_path / "b" / "dev", "x.json", "old-b")
    new_a = _dir(tmp_path / "a" / "dev.recording", "x.json", "new-a")
    new_b = _dir(tmp_path / "b" / "dev.recording", "x.json", "new-b")
    swap_in([(new_a, old_a), (new_b, old_b)])
    assert (old_a / "x.json").read_text() == "new-a"
    assert (old_b / "x.json").read_text() == "new-b"
    assert not new_a.exists() and not new_b.exists()
    assert not list(tmp_path.rglob("*.previous"))


def test_works_when_there_is_no_previous_recording(tmp_path: Path) -> None:
    new = _dir(tmp_path / "a" / "dev.recording", "x.json", "new")
    swap_in([(new, tmp_path / "a" / "dev")])
    assert (tmp_path / "a" / "dev" / "x.json").read_text() == "new"


def test_a_failure_in_the_second_swap_restores_the_first(tmp_path: Path) -> None:
    old_a = _dir(tmp_path / "a" / "dev", "x.json", "old-a")
    old_b = _dir(tmp_path / "b" / "dev", "x.json", "old-b")
    new_a = _dir(tmp_path / "a" / "dev.recording", "x.json", "new-a")
    missing_b = tmp_path / "b" / "dev.recording"  # never staged: its rename will fail
    with pytest.raises(FileNotFoundError):
        swap_in([(new_a, old_a), (missing_b, old_b)])
    assert (old_a / "x.json").read_text() == "old-a"
    assert (old_b / "x.json").read_text() == "old-b"
