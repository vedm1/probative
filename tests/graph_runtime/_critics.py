"""Scripted critics for the runtime tests: no model, no key."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel

from probative.core.critic import Finding, Rubric, RubricCheck, Severity
from probative.critics.base import Critic
from probative.llm.types import TokenUsage


def rubric(
    rubric_id: str, applies_to: list[str] | None = None, severity: Severity = Severity.BLOCK
) -> Rubric:
    return Rubric(
        id=rubric_id,
        severity=severity,
        invariant="I3",
        applies_to=applies_to or [],
        checks=[RubricCheck(id="bad", description="d", remedy="fix it")],
        clean_fixtures="c/*.json",
        defect_fixtures="d/*.json",
    )


@dataclass
class Stats:
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(input_tokens=0, output_tokens=0))


class ScriptedCritic(Critic):
    """Flags every candidate whose text satisfies `flag`. Records what it saw."""

    def __init__(
        self,
        rubric_id: str,
        *,
        flag: Callable[[BaseModel], bool] = lambda c: False,
        severity: Severity | None = None,
        applies_to: list[str] | None = None,
        delay: float = 0.0,
        tokens: int = 0,
        boom: Exception | None = None,
    ) -> None:
        super().__init__(rubric(rubric_id, applies_to))
        self._flag, self._severity, self._delay = flag, severity, delay
        self._tokens, self._boom = tokens, boom
        self.seen: list[str] = []
        self.calls = 0
        self.stats = Stats()
        self._lock = threading.Lock()

    def check(self, candidates: Sequence[BaseModel]) -> list[Finding]:
        with self._lock:
            self.calls += 1
        time.sleep(self._delay)
        if self._boom is not None:
            raise self._boom
        self.stats.usage = TokenUsage(
            input_tokens=self.stats.usage.input_tokens + self._tokens, output_tokens=0
        )
        out: list[Finding] = []
        for cand in candidates:
            self.seen.append(getattr(cand, "id", ""))
            if self._flag(cand):
                out.append(
                    self._finding(
                        check_id="bad",
                        message=f"flagged {getattr(cand, 'text', '')}",
                        severity=self._severity,
                        target_id=getattr(cand, "id", None),
                    )
                )
        return out
