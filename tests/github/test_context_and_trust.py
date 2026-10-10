"""PB35-p1: reading the Actions event and deciding whether to run at all."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from probative.interfaces.github.context import ContextError, load_context
from probative.interfaces.github.trust import decide
from tests.github.conftest import EVENTS


def test_same_repo_event_is_parsed() -> None:
    ctx = load_context(EVENTS / "pull_request_same_repo.json", "pull_request")
    assert (ctx.repo, ctx.number, ctx.head_repo) == ("acme/specs", 7, "acme/specs")
    assert ctx.head_sha == "1" * 40
    assert ctx.author_login == "alice"
    assert ctx.author_association == "MEMBER"
    assert not ctx.is_fork


def test_fork_event_is_a_fork() -> None:
    ctx = load_context(EVENTS / "pull_request_fork.json", "pull_request")
    assert ctx.is_fork


def test_same_repo_pull_request_runs() -> None:
    ctx = load_context(EVENTS / "pull_request_same_repo.json", "pull_request")
    decision = decide(ctx)
    assert decision.allowed


def test_fork_pull_request_is_refused_with_a_reason() -> None:
    ctx = load_context(EVENTS / "pull_request_fork.json", "pull_request")
    decision = decide(ctx)
    assert not decision.allowed
    assert "fork" in decision.reason


def test_pull_request_target_is_refused_until_p2() -> None:
    ctx = load_context(EVENTS / "pull_request_same_repo.json", "pull_request_target")
    decision = decide(ctx)
    assert not decision.allowed
    assert "pull_request_target" in decision.reason


def test_an_event_that_is_not_a_pull_request_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "push.json"
    path.write_text(json.dumps({"ref": "refs/heads/main"}))
    with pytest.raises(ContextError, match="pull request"):
        load_context(path, "pull_request")


def test_a_missing_event_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ContextError):
        load_context(tmp_path / "nope.json", "pull_request")


def test_an_unsupported_event_name_is_an_error() -> None:
    with pytest.raises(ContextError, match="pull_request"):
        load_context(EVENTS / "pull_request_same_repo.json", "issue_comment")
