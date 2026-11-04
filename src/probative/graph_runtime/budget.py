"""Per-phase token and wall-clock budgets (docs/DESIGN.md §9.1).

Wall-clock counts *compute* seconds the run spent, not the days a gate sat open:
a monotonic clock does not survive a process, and a person's thinking time is not
the system's cost. On exhaustion the runtime degrades explicitly and records it;
it never truncates silently.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetView:
    tokens_left: int
    seconds_left: float

    @property
    def exhausted(self) -> bool:
        return self.tokens_left <= 0 or self.seconds_left <= 0.0


class BudgetLedger:
    def __init__(
        self,
        *,
        token_budget: int,
        wall_seconds: float,
        spent_tokens: int = 0,
        spent_seconds: float = 0.0,
    ) -> None:
        self.token_budget = token_budget
        self.wall_seconds = wall_seconds
        self.spent_tokens = spent_tokens
        self.spent_seconds = spent_seconds

    def charge(self, *, tokens: int, seconds: float) -> None:
        if tokens < 0 or seconds < 0:
            raise ValueError("a charge cannot be negative")
        self.spent_tokens += tokens
        self.spent_seconds += seconds

    def view(self) -> BudgetView:
        return BudgetView(
            tokens_left=max(0, self.token_budget - self.spent_tokens),
            seconds_left=max(0.0, self.wall_seconds - self.spent_seconds),
        )
