"""Run critics in parallel and join their findings (docs/DESIGN.md §9.1).

`probative.critics.runner.run_critics` is the sequential reference. This is the
runtime's version: one thread per critic, results joined in the order the
critics were given, so the same inputs always give the same findings in the
same order. A critic that raises is a `block` finding, never a swallowed
exception and never a silent pass: a critic that could not run cannot clear a
patch.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import BaseModel

from probative.core.critic import Finding, Severity
from probative.critics.base import Critic

CriticJob = tuple[str, Critic, Sequence[BaseModel]]


@dataclass(frozen=True)
class FanoutResult:
    findings: list[Finding]
    tokens: int


def _used(critic: Critic) -> int:
    stats = getattr(critic, "stats", None)
    usage = getattr(stats, "usage", None)
    return int(usage.total_tokens) if usage is not None else 0


def _relevant(critic: Critic, candidates: Sequence[BaseModel]) -> list[BaseModel]:
    applies_to = critic.rubric.applies_to
    if not applies_to:
        return list(candidates)
    return [c for c in candidates if type(c).__name__ in applies_to]


def _run_one(job: CriticJob) -> tuple[list[Finding], int]:
    critic_id, critic, candidates = job
    relevant = _relevant(critic, candidates)
    if not relevant:
        return [], 0
    before = _used(critic)
    try:
        found = critic.check(relevant)
    except Exception as err:
        return [
            Finding(
                critic_id=critic_id,
                check_id="critic_error",
                severity=Severity.BLOCK,
                invariant=None,
                message=f"{type(err).__name__}: {err}",
                remedy="Re-run the critic. A critic that could not run cannot clear a patch.",
            )
        ], max(0, _used(critic) - before)
    return found, max(0, _used(critic) - before)


def run_critic_fanout(jobs: Sequence[CriticJob], *, workers: int = 8) -> FanoutResult:
    if not jobs:
        return FanoutResult([], 0)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs)))) as pool:
        results = list(pool.map(_run_one, jobs))
    findings = [f for found, _ in results for f in found]
    return FanoutResult(findings, sum(tokens for _, tokens in results))
