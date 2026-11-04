"""Run half of a gated phase in this process. Used by test_probes to prove a
gate resumes from `checkpoint.sqlite` in a different process.

    python -m tests.graph_runtime._cross_process <run-parent-dir> start|accept
"""

from __future__ import annotations

import sys
from pathlib import Path

from probative.graph_runtime.gates import GateDecision
from probative.graph_runtime.phases import Phase
from tests.graph_runtime._agents import ScriptedAgent
from tests.graph_runtime._harness import good, runtime


def main(argv: list[str]) -> int:
    base, command = Path(argv[0]), argv[1]
    rt = runtime(base, {Phase.P2: ScriptedAgent(good)})
    try:
        if command == "start":
            print(rt.start(Phase.P2).status)
        else:
            pending = rt.pending(Phase.P2)
            assert pending is not None
            out = rt.decide(Phase.P2, GateDecision(kind="accept"), patch_id=pending.patch.id)
            print(out.status, out.graph_hash)
    finally:
        rt.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
