"""Fan a batch of candidates out to a set of critics."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from probative.core.critic import Finding
from probative.critics.base import Critic


def run_critics(critics: Sequence[Critic], candidates: Sequence[BaseModel]) -> list[Finding]:
    """Run every critic against the candidates its rubric applies to.

    A rubric's `applies_to` names candidate class names; a candidate is
    passed to a critic only if `type(candidate).__name__` is in that list,
    or the list is empty (meaning "every candidate"). Findings from every
    critic are concatenated in the order `critics` was given.

    Sequential by design — true parallel fan-out is PB12's LangGraph
    runtime concern, not this framework's.
    """
    findings: list[Finding] = []
    for critic in critics:
        applies_to = critic.rubric.applies_to
        relevant = (
            list(candidates)
            if not applies_to
            else [c for c in candidates if type(c).__name__ in applies_to]
        )
        if relevant:
            findings.extend(critic.check(relevant))
    return findings
