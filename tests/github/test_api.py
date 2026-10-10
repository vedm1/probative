"""PB35-p1: the stdlib REST client, against the fake GitHub."""

from __future__ import annotations

import pytest

from probative.interfaces.github.api import GitHubClient, GitHubError
from tests.github.conftest import HEAD_SHA, REPO, FakeGitHub

TOKEN = "ghs_secret_token_value_123"


def _client(github: FakeGitHub) -> GitHubClient:
    return GitHubClient(github.url, TOKEN)


def test_files_are_paged_until_a_short_page(github: FakeGitHub) -> None:
    for i in range(230):
        github.add_file(f"docs/f{i:03}.md", f"line {i}\n")
    files = _client(github).list_pr_files(REPO, 7)
    assert len(files) == 230
    assert files[0].path == "docs/f000.md" and files[0].status == "added"
    assert files[0].patch is not None
    pages = [r.query["page"][0] for r in github.requests if r.path.endswith("/files")]
    assert pages == ["1", "2", "3"]


def test_a_file_without_a_patch_has_none(github: FakeGitHub) -> None:
    github.add_file("big.md", "x\n", patch=None)
    assert _client(github).list_pr_files(REPO, 7)[0].patch is None


def test_file_contents_are_read_raw_at_the_given_sha(github: FakeGitHub) -> None:
    github.add_file("docs/my spec ü.md", "héllo\n")
    data = _client(github).get_file(REPO, "docs/my spec ü.md", HEAD_SHA)
    assert data == "héllo\n".encode()
    request = github.requests[-1]
    assert request.query["ref"] == [HEAD_SHA]
    assert request.headers["accept"] == "application/vnd.github.raw+json"


def test_the_token_is_sent_as_a_bearer_credential(github: FakeGitHub) -> None:
    github.add_file("a.md", "x\n")
    _client(github).list_pr_files(REPO, 7)
    assert github.requests[-1].headers["authorization"] == f"Bearer {TOKEN}"


def test_a_missing_file_is_a_github_error_with_its_status(github: FakeGitHub) -> None:
    with pytest.raises(GitHubError) as caught:
        _client(github).get_file(REPO, "nope.md", HEAD_SHA)
    assert caught.value.status == 404


def test_an_error_never_carries_the_token(github: FakeGitHub) -> None:
    github.echo_auth_in_errors = True
    with pytest.raises(GitHubError) as caught:
        _client(github).list_pr_files(REPO, 8)
    assert TOKEN not in str(caught.value)


def test_a_refused_connection_is_a_github_error() -> None:
    with pytest.raises(GitHubError) as caught:
        GitHubClient("http://127.0.0.1:9", TOKEN).list_pr_files(REPO, 7)
    assert caught.value.status == 0


def test_create_review_sends_event_commit_and_ranges(github: FakeGitHub) -> None:
    _client(github).create_review(
        REPO,
        7,
        HEAD_SHA,
        [
            {"path": "a.md", "line": 3, "side": "RIGHT", "body": "one"},
            {"path": "a.md", "line": 5, "start_line": 4, "side": "RIGHT", "body": "two"},
        ],
    )
    body = github.reviews()[0].body
    assert body["event"] == "COMMENT" and body["commit_id"] == HEAD_SHA
    assert body["comments"][1]["start_line"] == 4 and "start_line" not in body["comments"][0]
    assert "body" not in body


def test_a_rejected_review_raises_422(github: FakeGitHub) -> None:
    github.reject_review_with_422 = True
    with pytest.raises(GitHubError) as caught:
        _client(github).create_review(
            REPO, 7, HEAD_SHA, [{"path": "a.md", "line": 3, "side": "RIGHT", "body": "x"}]
        )
    assert caught.value.status == 422


def test_issue_comments_are_created_and_patched(github: FakeGitHub) -> None:
    client = _client(github)
    made = client.create_issue_comment(REPO, 7, "first")
    client.update_issue_comment(REPO, made["id"], "second")
    assert github.issue_comments[0]["body"] == "second"
    assert client.list_issue_comments(REPO, 7)[0]["body"] == "second"
    assert client.list_review_comments(REPO, 7) == []


def test_an_unreadable_success_body_is_a_github_error(github: FakeGitHub) -> None:
    github.files.append({"status": "added"})  # no filename
    with pytest.raises(GitHubError):
        _client(github).list_pr_files(REPO, 7)
