"""What an agent is shown, and what the checkpoint holds.

`GraphState` and `RunContext` are handed to an agent: a read-only view of the
graph and the means to do its work. `RunState` is different: it is what LangGraph
writes to the checkpoint, so it holds **only JSON primitives** (probed: a pydantic
model in checkpoint state logs a deprecation for a future strict mode). Patches,
findings and graphs live on disk; the state holds ids and hashes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from probative.core.critic import Finding
from probative.core.graph.graph import Graph
from probative.core.graph.validators import Violation
from probative.graph_runtime.budget import BudgetView
from probative.graph_runtime.gates import GateRejectReason
from probative.graph_runtime.modes import Mode
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.tedium import InteractionLog
from probative.llm import Provider


@dataclass(frozen=True)
class GraphState:
    """Read-only: the committed graph plus why the last attempt was sent back."""

    graph: Graph
    phase: Phase
    mode: Mode
    cycle: int
    prior_findings: tuple[Finding, ...] = ()
    prior_violations: tuple[Violation, ...] = ()
    reject_reason: GateRejectReason | None = None


@dataclass(frozen=True)
class RunContext:
    provider: Provider | None
    model: str
    run_dir: Path
    source_root: Path
    clock: Callable[[], datetime]
    budget: BudgetView
    interactions: InteractionLog


class RunState(TypedDict, total=False):
    run_id: str
    phase: str
    mode: str
    cycle: int
    patch_id: str
    graph_hash: str
    findings: list[dict[str, Any]]
    violations: list[dict[str, str]]
    blocking: bool
    route: str
    gate_decision: dict[str, Any] | None
    reject_reason: str | None
    pending_since: str | None
    spent_tokens: int
    spent_seconds: float
    status: str
