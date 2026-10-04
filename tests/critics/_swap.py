"""Swapping freshly recorded directories into place without ever leaving a good
recording nowhere."""

from __future__ import annotations

import shutil
from pathlib import Path


def swap_in(staged: list[tuple[Path, Path]]) -> None:
    """Replace each recording directory with its staged one. The old directory is
    moved aside, not deleted, until its replacement is in place; if a swap
    fails the old ones are restored, so there is no state in which a good
    recording exists nowhere."""
    done: list[tuple[Path, Path]] = []  # (directory, backup)
    try:
        for staging, directory in staged:
            backup = directory.with_name(f"{directory.name}.previous")
            shutil.rmtree(backup, ignore_errors=True)
            if directory.exists():
                directory.rename(backup)
            done.append((directory, backup))
            staging.rename(directory)
    except BaseException:
        for directory, backup in reversed(done):
            if backup.exists():
                shutil.rmtree(directory, ignore_errors=True)
                backup.rename(directory)
        raise
    for _, backup in done:
        shutil.rmtree(backup, ignore_errors=True)
