"""A minimal candidate type and critic, used only to prove the PB3 framework
works end-to-end. Not a real critic — see PB5-PB8 for those.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from probative.core.critic import Finding
from probative.critics.base import Critic


class Note(BaseModel):
    id: str
    text: str


class NonEmptyTextCritic(Critic):
    """Flags a Note whose text is empty or whitespace-only."""

    def check(self, candidates: Sequence[BaseModel]) -> list[Finding]:
        findings = []
        for candidate in candidates:
            assert isinstance(candidate, Note)
            if not candidate.text.strip():
                findings.append(
                    self._finding(
                        check_id="non_empty_text",
                        message=f"{candidate.id}: text is empty or whitespace-only",
                        target_id=candidate.id,
                    )
                )
        return findings


def parse_notes(path: Path) -> list[Note]:
    return [Note.model_validate(raw) for raw in json.loads(path.read_text())]
