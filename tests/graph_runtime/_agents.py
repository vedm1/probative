"""A scripted producer: no model, no key. Records what it was shown."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from probative.agents.contract import AgentResult, TierPolicy
from probative.graph_runtime.state import GraphState, RunContext
from tests.graph_runtime._support import ALL_TIERS

Produce = Callable[[GraphState, RunContext], AgentResult]


class Empty(BaseModel):
    pass


class ScriptedAgent:
    input_model = Empty
    output_model = Empty
    tools = ()

    def __init__(
        self, produce: Produce, *, name: str = "scripted", policy: TierPolicy = ALL_TIERS
    ) -> None:
        self.name = name
        self.tier_policy = policy
        self._produce = produce
        self.states: list[GraphState] = []

    @property
    def calls(self) -> int:
        return len(self.states)

    def run(self, state: GraphState, ctx: RunContext) -> AgentResult:
        self.states.append(state)
        return self._produce(state, ctx)
