"""The agent contract (PROBATIVE_PHASE_SPECS.md S1).

An agent proposes; it never writes. `AgentResult` is the whole of what an agent
returns: a patch of nodes and edges, an audit trail of the tools it called, and
what it was least sure about. The `Committer` (`probative.graph_runtime`) is the
only thing that turns a patch into graph state.

I4: an agent may propose formula *inputs*, never *outputs*. Every `Computed` it
proposes carries `value=None`; the Committer fills it by calling the registered
formula. `CostRecord` holds measured usage (tokens, seconds), which is neither a
graph value nor a score.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from probative.core.evidence import Tier
from probative.core.graph.edges import Edge
from probative.core.graph.nodes import Node

if TYPE_CHECKING:
    from probative.graph_runtime.state import GraphState, RunContext

Tool = Callable[..., object]
"""A deterministic function an agent may call."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ToolCall(_Frozen):
    """One audited call. A formula call appears here with its inputs."""

    name: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    output_ref: str = ""


class CostRecord(_Frozen):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    wall_seconds: float = Field(ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class SelfAssessment(_Frozen):
    """What the agent was least sure about. Kept in the run record (the
    assumption ledger), not in the graph: whether it ships in an artifact is
    OI10 / PB29's decision."""

    least_sure_about: tuple[str, ...] = ()


class TierPolicy(_Frozen):
    """The evidence tiers an agent may rest a patch on."""

    allowed: frozenset[Tier]


class AgentResult(_Frozen):
    proposed_nodes: tuple[Node, ...] = ()
    proposed_edges: tuple[Edge, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()
    rationale: str = ""
    self_assessment: SelfAssessment = SelfAssessment()
    cost: CostRecord


class Agent(Protocol):
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    tools: Sequence[Tool]
    tier_policy: TierPolicy

    def run(self, state: GraphState, ctx: RunContext) -> AgentResult: ...
