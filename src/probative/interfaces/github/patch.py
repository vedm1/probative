"""Which new-side lines a pull request's `patch` shows (PB35).

GitHub accepts a review comment only on a line that appears in the diff, so the
action needs the set of lines it may comment on (`visible`) and the set the PR
actually wrote (`added`). Both are new-file line numbers.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchMap(BaseModel):
    model_config = ConfigDict(frozen=True)

    added: frozenset[int]
    visible: frozenset[int]


def parse_patch(patch: str) -> PatchMap:
    """The hunk header's counts say where each hunk ends, so a trailing newline or a blank
    context line that lost its leading space cannot be mistaken for an extra line."""
    added: set[int] = set()
    visible: set[int] = set()
    line_no = 0
    old_left = new_left = 0
    for raw in patch.split("\n"):
        header = _HUNK.match(raw)
        if header:
            old_left = 1 if header.group(1) is None else int(header.group(1))
            line_no = int(header.group(2))
            new_left = 1 if header.group(3) is None else int(header.group(3))
            continue
        if raw.startswith("\\") or (old_left <= 0 and new_left <= 0):
            continue
        if raw.startswith("+"):
            added.add(line_no)
            visible.add(line_no)
            line_no += 1
            new_left -= 1
        elif raw.startswith("-"):
            old_left -= 1
        else:  # context; a blank one may have lost its leading space
            visible.add(line_no)
            line_no += 1
            old_left -= 1
            new_left -= 1
    return PatchMap(added=frozenset(added), visible=frozenset(visible))
