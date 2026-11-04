"""A patch: what an agent proposed, content-addressed, kept on disk.

The checkpoint holds only a patch id; the patch itself lives in
`runs/<id>/patches/`. A rejected patch is kept in `runs/<id>/rejected/` with the
findings and violations that rejected it (S1).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from probative.agents.contract import AgentResult
from probative.core.critic import Finding
from probative.core.graph.validators import Violation
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.runfiles import RunFiles, write_json_atomic


class Patch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    agent: str
    phase: Phase
    cycle: int
    result: AgentResult

    @classmethod
    def build(cls, agent: str, phase: Phase, cycle: int, result: AgentResult) -> Self:
        """The id is a hash of the proposed nodes and edges alone: the same
        proposal has the same id whichever cycle or agent made it."""
        body = {
            "nodes": [n.model_dump(mode="json") for n in result.proposed_nodes],
            "edges": [e.model_dump(mode="json") for e in result.proposed_edges],
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(id=f"patch_{digest[:12]}", agent=agent, phase=phase, cycle=cycle, result=result)


class PatchStore:
    def __init__(self, files: RunFiles) -> None:
        self._files = files

    def save(self, patch: Patch) -> Path:
        path = self._files.patches_dir / f"{patch.id}.json"
        write_json_atomic(path, patch.model_dump(mode="json"))
        return path

    def load(self, patch_id: str) -> Patch:
        path = self._files.patches_dir / f"{patch_id}.json"
        return Patch.model_validate_json(path.read_text("utf-8"))

    def save_rejected(
        self, patch: Patch, findings: Sequence[Finding], violations: Sequence[Violation]
    ) -> Path:
        path = self._files.rejected_dir / f"{patch.id}-c{patch.cycle}.json"
        write_json_atomic(
            path,
            {
                "patch": patch.model_dump(mode="json"),
                "findings": [f.model_dump(mode="json") for f in findings],
                "violations": [asdict(v) for v in violations],
            },
        )
        return path
