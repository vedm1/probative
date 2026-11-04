"""Where a run keeps its files. One directory, gitignored (`runs/`)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunFiles:
    root: Path

    @property
    def graph_path(self) -> Path:
        return self.root / "graph.json"

    @property
    def mirror_path(self) -> Path:
        return self.root / "graph.sqlite"

    @property
    def ledger_path(self) -> Path:
        return self.root / "commits.jsonl"

    @property
    def checkpoint_path(self) -> Path:
        """LangGraph's checkpoint. Not derived and not disposable: a paused gate
        lives here. The graph mirror (`mirror_path`) is the disposable one."""
        return self.root / "checkpoint.sqlite"

    @property
    def interactions_path(self) -> Path:
        return self.root / "interactions.jsonl"

    @property
    def patches_dir(self) -> Path:
        return self.root / "patches"

    @property
    def rejected_dir(self) -> Path:
        return self.root / "rejected"

    @property
    def assumptions_path(self) -> Path:
        return self.root / "assumptions.jsonl"

    def ensure(self) -> None:
        for d in (self.root, self.patches_dir, self.rejected_dir):
            d.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_jsonl(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
