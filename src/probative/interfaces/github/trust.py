"""Whether to run at all (PB35).

p1 runs only where the token can write and the secret exists: a same-repo
`pull_request`. A fork `pull_request` has neither, so it is a notice and a clean exit.
`pull_request_target` (which has both, for code the repo does not control) is p2's
trust gate and is refused here rather than half-supported.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from probative.interfaces.github.context import PullRequestContext


class TrustDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: str
    restrict_formats: bool = False


def decide(ctx: PullRequestContext) -> TrustDecision:
    if ctx.event_name == "pull_request_target":
        return TrustDecision(
            allowed=False,
            reason="pull_request_target is not supported yet; use the pull_request event",
        )
    if ctx.is_fork:
        return TrustDecision(
            allowed=False,
            reason=(
                f"pull request from the fork {ctx.head_repo or 'unknown'}: forks get no secrets "
                "and a read-only token on pull_request, so nothing was reviewed"
            ),
        )
    return TrustDecision(allowed=True, reason="pull request from this repository")
