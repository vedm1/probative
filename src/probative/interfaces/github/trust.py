"""Whether to run at all (PB35).

`pull_request` runs where the token can write and the secret exists: a same-repo PR. A fork
`pull_request` has neither, so it is a notice and a clean exit.

`pull_request_target` has both, for code the repository does not control, so it is gated
twice. A trusted author (owner, member, collaborator) runs. Anyone else runs only when a
maintainer applies the configured label, judged by the *sender's* write permission, and then
only over text formats (the runner enforces that). Every doubt is a refusal: the permission
lookup failing, an unknown value, a label other than the configured one. A refusal is cheap;
a run on an outsider's files is paid for with the key.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from probative.interfaces.github.api import GitHubError
from probative.interfaces.github.context import PullRequestContext

DEFAULT_LABEL = "probative-review"
# MEMBER is any org member and COLLABORATOR includes read and triage roles: neither means
# write access, so only OWNER is trusted by association alone.
ALWAYS_TRUSTED = frozenset({"OWNER"})
CHECKED_ASSOCIATIONS = frozenset({"MEMBER", "COLLABORATOR"})
WRITE_PERMISSIONS = frozenset({"admin", "write"})
# `closed`, `edited`, `assigned` and the rest are not a reason to spend tokens
_TARGET_ACTIONS = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})

PermissionLookup = Callable[[str], str]


class TrustDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: str
    # the safe default: a decision built by hand never lets a binary parser run
    restrict_formats: bool = True


def _refuse(reason: str) -> TrustDecision:
    return TrustDecision(allowed=False, reason=reason)


def decide(
    ctx: PullRequestContext,
    *,
    label: str = DEFAULT_LABEL,
    permission_of: PermissionLookup | None = None,
) -> TrustDecision:
    if ctx.event_name == "pull_request_target":
        return _decide_target(ctx, label, permission_of)
    if ctx.is_fork:
        return _refuse(
            f"pull request from the fork {ctx.head_repo or 'unknown'}: forks get no secrets "
            "and a read-only token on pull_request, so nothing was reviewed"
        )
    return TrustDecision(
        allowed=True, reason="pull request from this repository", restrict_formats=False
    )


def _has_write(permission_of: PermissionLookup | None, login: str) -> bool:
    if permission_of is None:
        return False
    try:
        return permission_of(login) in WRITE_PERMISSIONS
    except GitHubError:
        return False


def _decide_target(
    ctx: PullRequestContext, label: str, permission_of: PermissionLookup | None
) -> TrustDecision:
    labeled = ctx.action == "labeled"
    if not label:
        return _refuse("no label is configured to start a review")
    if labeled and ctx.event_label != label:
        return _refuse(f"the label {ctx.event_label!r} was applied; only {label!r} starts a review")
    author_trusted = ctx.author_association in ALWAYS_TRUSTED or (
        ctx.author_association in CHECKED_ASSOCIATIONS
        and _has_write(permission_of, ctx.author_login)
    )
    if author_trusted:
        if labeled or ctx.action in _TARGET_ACTIONS:
            return TrustDecision(
                allowed=True,
                reason=f"pull request by an author with write access ({ctx.author_association})",
                restrict_formats=False,
            )
        return _refuse(f"the {ctx.action!r} action does not start a review")
    if not labeled:
        return _refuse(
            f"{ctx.author_login or 'the author'} has no write access here; "
            f"a maintainer starts a review by applying the {label!r} label"
        )
    if permission_of is None:
        return _refuse("could not check whether the label was applied by someone with write access")
    try:
        permission = permission_of(ctx.sender_login)
    except GitHubError as error:
        return _refuse(
            f"could not check {ctx.sender_login}'s permission, so no review was started ({error})"
        )
    if permission not in WRITE_PERMISSIONS:
        return _refuse(
            f"{ctx.sender_login} applied the label without write permission on this repository"
        )
    return TrustDecision(
        allowed=True,
        reason=f"{label!r} applied by {ctx.sender_login} (write access); text formats only",
        restrict_formats=True,
    )
