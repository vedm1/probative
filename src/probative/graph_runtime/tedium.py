"""Interaction counters and the `TediumAuditor` (I6, docs/DESIGN.md §9.5).

It counts how often the system interrupted a person and compares that with the
phase budgets. It does not decide anything and it does not block: a system that
imposes work on its user should measure it, and say so when it overreaches.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from probative.core.critic import Finding, Severity
from probative.graph_runtime.phases import Phase, PhaseSpec
from probative.graph_runtime.runfiles import append_jsonl, read_jsonl

RUN_INTERACTION_BUDGET = 40
RUN_GATE_BUDGET = 5
"""Full solo run: at most 40 interactions, at most 5 of them gates (DESIGN §9.5)."""


@dataclass(frozen=True)
class Interaction:
    phase: Phase
    kind: Literal["gate", "escalation"]
    seconds: float
    patch_id: str | None = None
    decision: dict[str, Any] | None = None
    """What the person answered, so the trail says who approved which patch."""


class InteractionLog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def record(self, item: Interaction) -> None:
        append_jsonl(self._path, asdict(item))

    def entries(self) -> list[Interaction]:
        return [
            Interaction(
                Phase(d["phase"]),
                d["kind"],
                float(d["seconds"]),
                d.get("patch_id"),
                d.get("decision"),
            )
            for d in read_jsonl(self._path)
        ]


class TediumAuditor:
    CRITIC_ID = "tedium_auditor"

    def audit(
        self, entries: Sequence[Interaction], phases: Mapping[Phase, PhaseSpec]
    ) -> list[Finding]:
        findings: list[Finding] = []
        per_phase = Counter(i.phase for i in entries)
        for phase in sorted(per_phase):
            budget = phases[phase].interaction_budget
            if per_phase[phase] > budget:
                findings.append(
                    self._finding(
                        "phase_over_budget",
                        Severity.WARN,
                        f"{phase.value} interrupted a person {per_phase[phase]} times; "
                        f"its budget is {budget}",
                    )
                )
        gates = sum(1 for i in entries if i.kind == "gate")
        if gates > RUN_GATE_BUDGET:
            findings.append(
                self._finding(
                    "run_gates_over_budget",
                    Severity.WARN,
                    f"{gates} gates in one run; the budget is {RUN_GATE_BUDGET}",
                )
            )
        if len(entries) > RUN_INTERACTION_BUDGET:
            findings.append(
                self._finding(
                    "run_over_budget",
                    Severity.WARN,
                    f"{len(entries)} interactions in one run; the budget is "
                    f"{RUN_INTERACTION_BUDGET}",
                )
            )
        findings.append(
            self._finding(
                "interaction_count",
                Severity.NOTE,
                f"{len(entries)} interactions, {gates} of them gates",
            )
        )
        return findings

    @classmethod
    def _finding(cls, check_id: str, severity: Severity, message: str) -> Finding:
        return Finding(
            critic_id=cls.CRITIC_ID,
            check_id=check_id,
            severity=severity,
            invariant="I6",
            message=message,
            remedy="Make the step a decision the system proposes, or remove it.",
        )
