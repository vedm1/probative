from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

from probative.agents.contract import Agent
from probative.core.graph.edges import Edge
from probative.core.graph.nodes import Need, NodeBase
from probative.critics.base import Critic
from probative.graph_runtime.modes import Mode
from probative.graph_runtime.phases import PHASES, Phase, PhaseSpec
from probative.graph_runtime.runtime import Runtime
from tests.core.graph._samples import ENV
from tests.graph_runtime._agents import ScriptedAgent
from tests.graph_runtime._support import clock, hypothesis_with_test, result


def need(text: str = "Reduce the time I spend re-keying data") -> Need:
    return Need.make(text=text, **ENV)


def good(state: object, ctx: object) -> object:
    return result([need()])


def phases(
    *, tokens: int = 200_000, critics: frozenset[str] | None = None
) -> dict[Phase, PhaseSpec]:
    table = {p: replace(s, token_budget=tokens) for p, s in PHASES.items()}
    if critics is not None:
        table = {p: replace(s, critics=critics) for p, s in table.items()}
    return table


def runtime(
    tmp_path: Path,
    agents: Mapping[Phase, Agent],
    *,
    mode: Mode = Mode.SOLO,
    critics: Mapping[str, Critic] | None = None,
    table: Mapping[Phase, PhaseSpec] | None = None,
    **kw: object,
) -> Runtime:
    return Runtime(
        tmp_path / "run1",
        source_root=tmp_path,
        mode=mode,
        agents=agents,
        critics=critics or {},
        phases=table or phases(critics=frozenset()),
        clock=clock,
        **kw,  # type: ignore[arg-type]
    )


def orphan_hypothesis() -> tuple[list[NodeBase], list[Edge]]:
    nodes, _ = hypothesis_with_test()
    return [nodes[0]], []


Fix = Callable[[int], tuple[list[NodeBase], list[Edge]]]


def agent_by_cycle(fix: Fix, *, name: str = "scripted") -> ScriptedAgent:
    def produce(state, ctx):  # type: ignore[no-untyped-def]
        nodes, edges = fix(state.cycle)
        return result(nodes, edges)

    return ScriptedAgent(produce, name=name)


def decide(rt: Runtime, phase: Phase, decision: object, **kw: object):  # type: ignore[no-untyped-def]
    """Answer whatever the run currently shows, as a person who looked at it would."""
    pending = rt.pending(phase)
    assert pending is not None
    return rt.decide(phase, decision, patch_id=pending.patch.id, **kw)  # type: ignore[arg-type]
