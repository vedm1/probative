"""T0: the LangGraph behaviours the runtime relies on, kept as tests.

Probed 2026-11-04 on langgraph 1.2.19 / langgraph-checkpoint-sqlite 3.1.3. If an
upgrade changes one of these, this file fails before a paused gate is lost.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from probative.core.graph import store
from probative.graph_runtime.gates import GateDecision
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.runfiles import RunFiles
from tests.graph_runtime._agents import ScriptedAgent
from tests.graph_runtime._harness import decide, good, runtime

ROOT = Path(__file__).resolve().parents[2]


def _run(base: Path, command: str, *, strict: bool = True) -> str:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT)}
    if strict:
        env["LANGGRAPH_STRICT_MSGPACK"] = "true"
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        env.pop(key, None)
    done = subprocess.run(
        [sys.executable, "-m", "tests.graph_runtime._cross_process", str(base), command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_a_gate_paused_in_one_process_resumes_in_another_with_the_same_graph(
    tmp_path: Path,
) -> None:
    """Gating check (2): killed at a gate, resumed in a new process, same hash.
    Strict msgpack is on, so a non-primitive in the checkpoint would fail here."""
    paused, straight = tmp_path / "paused", tmp_path / "straight"
    paused.mkdir()
    straight.mkdir()
    assert _run(paused, "start") == "awaiting_gate"
    assert not RunFiles(paused / "run1").graph_path.exists()
    status, digest = _run(paused, "accept").split()
    assert status == "committed"

    rt = runtime(straight, {Phase.P2: ScriptedAgent(good)})
    rt.start(Phase.P2)
    uninterrupted = decide(rt, Phase.P2, GateDecision(kind="accept"))
    assert digest == uninterrupted.graph_hash
    assert store.content_hash(store.read_graph(RunFiles(paused / "run1").graph_path)) == digest


def test_checkpoint_state_is_plain_json(tmp_path: Path) -> None:
    rt = runtime(tmp_path, {Phase.P2: ScriptedAgent(good)})
    rt.start(Phase.P2)
    snap = rt._app.get_state(rt._config(Phase.P2, 1))
    json.dumps(snap.values)  # raises on a non-primitive


def test_an_agent_that_raises_leaves_a_run_that_resumes(tmp_path: Path) -> None:
    calls = {"n": 0}

    def produce(state: object, ctx: object):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model unreachable")
        return good(state, ctx)

    rt = runtime(tmp_path, {Phase.P1: ScriptedAgent(produce)})
    with pytest.raises(RuntimeError, match="model unreachable"):
        rt.start(Phase.P1)
    assert not RunFiles(tmp_path / "run1").graph_path.exists()
    out = rt.resume(Phase.P1)
    assert out.status == "committed" and calls["n"] == 2


def test_a_second_start_of_the_same_attempt_is_refused(tmp_path: Path) -> None:
    from probative.graph_runtime.runtime import RunRefusedError

    rt = runtime(tmp_path, {Phase.P1: ScriptedAgent(good)})
    rt.start(Phase.P1)
    with pytest.raises(RunRefusedError, match="already exists"):
        rt.start(Phase.P1)
    assert rt.start(Phase.P1, attempt=2).status == "committed"


def test_three_repair_cycles_and_a_human_reject_fit_under_the_recursion_limit(
    tmp_path: Path,
) -> None:
    from probative.graph_runtime.gates import GateRejectReason
    from tests.graph_runtime._harness import agent_by_cycle, orphan_hypothesis

    agent = agent_by_cycle(lambda cycle: orphan_hypothesis())
    rt = runtime(tmp_path, {Phase.P1: agent})
    rt.start(Phase.P1)
    for _ in range(3):  # three human rejects, nine more repair cycles, no limit error
        decide(rt, Phase.P1, GateDecision(kind="reject", reason=GateRejectReason.OTHER))
    assert agent.calls == 12


def test_only_the_runtime_module_imports_langgraph() -> None:
    offenders = []
    for path in (ROOT / "src" / "probative").rglob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n.split(".")[0] == "langgraph" for n in names):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert set(offenders) == {"src/probative/graph_runtime/runtime.py"}


def test_importing_the_runtime_needs_no_credentials_and_no_network() -> None:
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    done = subprocess.run(
        [sys.executable, "-c", "import probative.graph_runtime.runtime"],
        cwd=ROOT,
        env={**env, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
