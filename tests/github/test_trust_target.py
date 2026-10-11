"""PB35-p2: who may spend the key on a `pull_request_target` run."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from probative.interfaces.github.api import GitHubClient, GitHubError
from probative.interfaces.github.context import load_context
from probative.interfaces.github.trust import decide
from tests.github.conftest import FakeGitHub, target_event

LABEL = "probative-review"


def _decide(
    tmp_path: Path, lookup: Callable[[str], str] | None = None, **event: str | None
) -> tuple[bool, str, bool]:
    ctx = load_context(target_event(tmp_path, **event), "pull_request_target")  # type: ignore[arg-type]
    decision = decide(ctx, label=LABEL, permission_of=lookup)
    return decision.allowed, decision.reason, decision.restrict_formats


def _raises(login: str) -> str:
    raise AssertionError("the permission lookup ran when it should not have")


def _author_has(permission: str) -> Callable[[str], str]:
    def lookup(login: str) -> str:
        assert login == "mallory", "only the author is looked up on an ordinary push"
        return permission

    return lookup


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened", "ready_for_review"])
def test_the_owner_runs_on_every_normal_action_with_all_formats(
    tmp_path: Path, action: str
) -> None:
    allowed, _, restricted = _decide(
        tmp_path, _raises, association="OWNER", action=action, label=None
    )
    assert allowed and not restricted


@pytest.mark.parametrize("association", ["MEMBER", "COLLABORATOR"])
@pytest.mark.parametrize("permission", ["write", "admin"])
@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened", "ready_for_review"])
def test_a_member_or_collaborator_with_write_runs_with_all_formats(
    tmp_path: Path, association: str, permission: str, action: str
) -> None:
    allowed, _, restricted = _decide(
        tmp_path, _author_has(permission), association=association, action=action, label=None
    )
    assert allowed and not restricted


@pytest.mark.parametrize("association", ["MEMBER", "COLLABORATOR"])
@pytest.mark.parametrize("permission", ["read", "none", ""])
def test_membership_alone_is_not_write_access(
    tmp_path: Path, association: str, permission: str
) -> None:
    # an org member or a triage collaborator can open a fork PR; they are an outsider here
    allowed, reason, _ = _decide(
        tmp_path, _author_has(permission), association=association, action="opened", label=None
    )
    assert not allowed and LABEL in reason


@pytest.mark.parametrize("association", ["MEMBER", "COLLABORATOR"])
def test_a_read_only_member_goes_through_the_label_path_with_text_only(
    tmp_path: Path, association: str
) -> None:
    def lookup(login: str) -> str:
        return "read" if login == "mallory" else "write"

    allowed, _, restricted = _decide(tmp_path, lookup, association=association)
    assert allowed and restricted


@pytest.mark.parametrize("association", ["MEMBER", "COLLABORATOR"])
def test_a_failed_author_lookup_makes_a_member_an_outsider(
    tmp_path: Path, association: str
) -> None:
    def broken(login: str) -> str:
        raise GitHubError(500, "boom")

    assert not _decide(tmp_path, broken, association=association, action="opened", label=None)[0]


def test_the_owner_runs_when_the_configured_label_is_applied(tmp_path: Path) -> None:
    allowed, _, restricted = _decide(tmp_path, _raises, association="OWNER")
    assert allowed and not restricted


def test_an_unrelated_label_never_starts_a_run_not_even_for_a_trusted_author(
    tmp_path: Path,
) -> None:
    allowed, reason, _ = _decide(tmp_path, _raises, association="OWNER", label="bug")
    assert not allowed and LABEL in reason


@pytest.mark.parametrize("action", ["closed", "edited", "assigned", "unlabeled", "locked"])
def test_other_actions_do_not_run(tmp_path: Path, action: str) -> None:
    allowed, _, _ = _decide(tmp_path, _raises, association="OWNER", action=action, label=None)
    assert not allowed


@pytest.mark.parametrize(
    "association", ["CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "NONE", "", "MANNEQUIN"]
)
@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened"])
def test_an_outsider_does_not_run_without_the_label_event(
    tmp_path: Path, association: str, action: str
) -> None:
    allowed, reason, _ = _decide(
        tmp_path, _raises, association=association, action=action, label=None
    )
    assert not allowed and LABEL in reason


@pytest.mark.parametrize("permission", ["admin", "write"])
def test_an_outsider_runs_when_a_maintainer_applies_the_label_with_text_formats_only(
    tmp_path: Path, permission: str
) -> None:
    asked: list[str] = []

    def lookup(login: str) -> str:
        asked.append(login)
        return permission

    allowed, _, restricted = _decide(tmp_path, lookup, sender="maintainer")
    assert allowed and restricted
    assert asked == ["maintainer"]  # the sender who applied it, not the PR author


@pytest.mark.parametrize("permission", ["read", "none", "triage", "", "ADMIN", "owner"])
def test_a_labeler_without_write_permission_does_not_start_a_run(
    tmp_path: Path, permission: str
) -> None:
    allowed, reason, _ = _decide(tmp_path, lambda login: permission)
    assert not allowed and "write" in reason


def test_a_failing_permission_lookup_fails_closed(tmp_path: Path) -> None:
    def broken(login: str) -> str:
        raise GitHubError(403, "Resource not accessible by integration")

    allowed, reason, _ = _decide(tmp_path, broken)
    assert not allowed and "403" in reason


def test_no_lookup_available_fails_closed(tmp_path: Path) -> None:
    assert _decide(tmp_path, None)[0] is False


def test_a_wrong_label_from_a_maintainer_does_not_start_a_run(tmp_path: Path) -> None:
    allowed, _, _ = _decide(tmp_path, _raises, label="wontfix")
    assert not allowed


def test_the_label_in_the_event_is_the_one_that_counts_not_the_labels_on_the_pr(
    tmp_path: Path,
) -> None:
    # the PR already carries the label, but this event applied another one
    path = target_event(tmp_path, label=LABEL)
    import json

    event = json.loads(path.read_text())
    event["label"] = {"name": "documentation"}
    path.write_text(json.dumps(event))
    ctx = load_context(path, "pull_request_target")
    assert ctx.event_label == "documentation"
    assert not decide(ctx, label=LABEL, permission_of=lambda login: "admin").allowed


def test_a_same_repo_pull_request_is_judged_by_association_not_by_where_it_came_from(
    tmp_path: Path,
) -> None:
    ctx = load_context(
        target_event(
            tmp_path, association="NONE", head_repo="acme/specs", action="opened", label=None
        ),
        "pull_request_target",
    )
    assert not decide(ctx, label=LABEL, permission_of=_raises).allowed


def test_pull_request_still_means_what_it_meant_in_p1(tmp_path: Path) -> None:
    ctx = load_context(target_event(tmp_path, association="OWNER"), "pull_request_target")
    # the same event body under the other name keeps the p1 rule: forks are refused
    fork = ctx.model_copy(update={"event_name": "pull_request"})
    assert not decide(fork, label=LABEL, permission_of=_raises).allowed


def test_the_label_name_is_empty_when_the_event_has_none(tmp_path: Path) -> None:
    ctx = load_context(target_event(tmp_path, action="opened", label=None), "pull_request_target")
    assert ctx.event_label == ""


def test_the_client_reads_the_labelers_permission_from_the_permission_endpoint(
    github: FakeGitHub,
) -> None:
    github.permissions["maint"] = "write"
    client = GitHubClient(github.url, "tok")
    assert client.collaborator_permission("acme/specs", "maint") == "write"
    assert github.requests[-1].path == "/repos/acme/specs/collaborators/maint/permission"


def test_a_login_cannot_change_the_permission_path(github: FakeGitHub) -> None:
    client = GitHubClient(github.url, "tok")
    client.collaborator_permission("acme/specs", "a/../../b")
    assert "/../" not in github.requests[-1].path
    assert github.requests[-1].path.count("/permission") == 1


def test_a_permission_error_carries_no_token(github: FakeGitHub) -> None:
    github.permission_status = 403
    with pytest.raises(GitHubError) as error:
        GitHubClient(github.url, "ghs_secret").collaborator_permission("acme/specs", "m")
    assert "ghs_secret" not in str(error.value)


def test_a_malformed_permission_body_is_an_error_not_a_pass(github: FakeGitHub) -> None:
    client = GitHubClient(github.url, "tok")
    github.permissions["m"] = ""  # the fake serves {"permission": ""}
    assert client.collaborator_permission("acme/specs", "m") == ""


def test_a_decision_restricts_formats_unless_it_says_otherwise() -> None:
    from probative.interfaces.github.trust import TrustDecision

    assert TrustDecision(allowed=True, reason="x").restrict_formats is True


def test_an_empty_configured_label_never_matches(tmp_path: Path) -> None:
    ctx = load_context(target_event(tmp_path, label=None, action="labeled"), "pull_request_target")
    assert not decide(ctx, label="", permission_of=lambda login: "admin").allowed


def test_the_label_match_is_exact(tmp_path: Path) -> None:
    ctx = load_context(target_event(tmp_path, label="Probative-Review"), "pull_request_target")
    assert not decide(ctx, label=LABEL, permission_of=lambda login: "admin").allowed


def test_a_malformed_label_in_the_event_is_a_context_error(tmp_path: Path) -> None:
    import json

    from probative.interfaces.github.context import ContextError

    path = target_event(tmp_path)
    event = json.loads(path.read_text())
    event["label"] = "probative-review"
    path.write_text(json.dumps(event))
    with pytest.raises(ContextError):
        load_context(path, "pull_request_target")
