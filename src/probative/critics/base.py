"""The `Critic` base class (PROBATIVE_PHASE_SPECS.md PB3): adding a critic
means writing a rubric (S2) and subclassing this with one method — `check`.
Nothing else in the runtime changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from pydantic import BaseModel

from probative.core.critic import Finding, Rubric, Severity, UnknownCheckError
from probative.core.evidence import EvidenceSpan


class Critic(ABC):
    """A rubric-configured check with veto authority over its findings'
    severity. Not an `Agent` (S1): it never proposes a patch and never
    touches the graph — it only returns `Finding`s.
    """

    def __init__(self, rubric: Rubric) -> None:
        self.rubric = rubric

    @abstractmethod
    def check(self, candidates: Sequence[BaseModel]) -> list[Finding]:
        """Evaluate candidates against this critic's rubric.

        Returns zero or more Findings. Never raises on a violation found in
        a candidate; never mutates a candidate.
        """
        raise NotImplementedError

    def _finding(
        self,
        *,
        check_id: str,
        message: str,
        severity: Severity | None = None,
        target_id: str | None = None,
        evidence: EvidenceSpan | None = None,
    ) -> Finding:
        """Construct a Finding against one of this critic's own declared
        checks, filling `critic_id`/`invariant`/`remedy` from the rubric.

        Raises `UnknownCheckError` if `check_id` is not declared in this
        critic's rubric — a typo here must fail loudly, not silently
        produce an undocumented finding.
        """
        matched = next((c for c in self.rubric.checks if c.id == check_id), None)
        if matched is None:
            raise UnknownCheckError(self.rubric.id, check_id)
        return Finding(
            critic_id=self.rubric.id,
            check_id=check_id,
            severity=severity or self.rubric.severity,
            invariant=self.rubric.invariant,
            message=message,
            remedy=matched.remedy,
            target_id=target_id,
            evidence=evidence,
        )
