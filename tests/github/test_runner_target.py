"""PB35-p2: an approved outsider's run reads the fork's text files and nothing else."""

from __future__ import annotations

from pathlib import Path

import pytest

from probative.critique.pipeline import CritiqueOptions
from probative.interfaces.github.api import ChangedFile, GitHubClient
from probative.interfaces.github.context import load_context
from probative.interfaces.github.runner import (
    UNTRUSTED_FORMATS,
    ActionOptions,
    RunResult,
    _critique_one,
    _FileSkipped,
    run_review,
)
from probative.interfaces.github.trust import TrustDecision, decide
from tests.critique._sample import DOC
from tests.critique._scripted import Scripted
from tests.github.conftest import HEAD_SHA, FakeGitHub, target_event

SPEC = "specs/checkout-prd.md"


def _run(
    github: FakeGitHub,
    tmp_path: Path,
    *,
    decision: TrustDecision | None = None,
    **event: str | None,
) -> RunResult:
    github.permissions["maintainer"] = "write"
    ctx = load_context(target_event(tmp_path, **event), "pull_request_target")  # type: ignore[arg-type]
    return run_review(
        ctx,
        decision or decide(ctx, label="probative-review", permission_of=lambda login: "write"),
        GitHubClient(github.url, "tok"),
        ActionOptions(),
        provider=Scripted(),
        critique_options=CritiqueOptions(model="test/model", jobs=2, clock=lambda: 0.0),
    )


def test_an_approved_outsider_run_reads_the_fork_at_the_head_sha(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.head_repo = "mallory/specs"
    github.add_file(SPEC, DOC)
    result = _run(github, tmp_path)
    reads = [r for r in github.requests if "/contents/" in r.path]
    assert reads and all(r.path.startswith("/repos/mallory/specs/contents/") for r in reads)
    assert all(r.query["ref"] == [HEAD_SHA] for r in reads)
    assert result.reviewed == 1 and len(github.issue_comments) == 1


def test_an_outsider_run_critiques_text_and_skips_every_binary_format_with_a_reason(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.head_repo = "mallory/specs"
    github.add_file(SPEC, DOC)
    for name in ("a.pdf", "b.docx", "c.xlsx"):
        github.add_file(f"specs/{name}", b"%PDF-not-really", patch=None)
    result = _run(github, tmp_path)
    fetched = {r.path.rsplit("/", 1)[-1] for r in github.requests if "/contents/" in r.path}
    assert fetched == {"checkout-prd.md"}  # a binary file is never even downloaded
    body = github.issue_comments[0]["body"]
    for name in ("a.pdf", "b.docx", "c.xlsx"):
        assert name in body
    assert "not allowed for authors without write access" in body
    assert {s.path for s in result.skipped} == {f"specs/{n}" for n in ("a.pdf", "b.docx", "c.xlsx")}


def test_a_trusted_run_still_reads_every_format(github: FakeGitHub, tmp_path: Path) -> None:
    github.head_repo = "mallory/specs"
    github.add_file("specs/a.pdf", b"%PDF-not-really", patch=None)
    _run(github, tmp_path, association="OWNER", action="opened", label=None)
    assert any(r.path.endswith("/specs/a.pdf") for r in github.requests)


def test_only_an_outsider_with_nothing_readable_posts_nothing_and_says_why(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.add_file("specs/a.pdf", b"x", patch=None)
    result = _run(github, tmp_path)
    assert github.writes() == []
    assert any("not allowed for authors without write access" in m for m in result.messages)


@pytest.mark.parametrize("name", ["a.pdf", "a.docx", "a.xlsx", "A.PDF", "a.md.pdf", "a"])
def test_the_fetch_point_refuses_a_restricted_format_even_if_the_filter_let_it_through(
    github: FakeGitHub, tmp_path: Path, name: str
) -> None:
    github.add_file(f"specs/{name}", b"x", patch=None)
    with pytest.raises(_FileSkipped, match="not allowed"):
        _critique_one(
            GitHubClient(github.url, "tok"),
            load_context(target_event(tmp_path), "pull_request_target"),
            ChangedFile(path=f"specs/{name}", status="added"),
            tmp_path / "w",
            Scripted(),
            CritiqueOptions(model="m"),
            restrict_formats=True,
        )
    assert not [r for r in github.requests if "/contents/" in r.path]


def test_the_allowed_suffixes_are_the_text_ones() -> None:
    assert set(UNTRUSTED_FORMATS) == {".md", ".markdown", ".txt"}


def test_a_refused_decision_makes_no_request(github: FakeGitHub, tmp_path: Path) -> None:
    github.add_file(SPEC, DOC)
    result = _run(github, tmp_path, decision=TrustDecision(allowed=False, reason="not approved"))
    assert github.requests == [] and result.exit_code == 0
    assert any("not approved" in m for m in result.messages)


def test_a_hand_built_allowed_decision_still_restricts_formats(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.add_file("specs/a.pdf", b"x", patch=None)
    _run(github, tmp_path, decision=TrustDecision(allowed=True, reason="by hand"))
    assert not [r for r in github.requests if "/contents/" in r.path]


def test_a_file_over_the_size_cap_is_skipped_for_an_outsider(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.head_repo = "mallory/specs"
    github.add_file("specs/huge.txt", "x" * (1024 * 1024 + 1), patch=None)
    result = _run(github, tmp_path)
    assert [s.reason for s in result.skipped] == ["over the 1 MB size cap for outside authors"]


def test_a_moved_head_is_a_notice_and_nothing_else(github: FakeGitHub, tmp_path: Path) -> None:
    github.head_repo = "mallory/specs"
    github.add_file(SPEC, DOC)
    github.pr_head_sha = "9" * 40
    result = _run(github, tmp_path)
    assert github.writes() == []
    assert not [r for r in github.requests if "/contents/" in r.path]
    assert any("head moved" in m for m in result.messages)


def test_an_unchanged_head_runs(github: FakeGitHub, tmp_path: Path) -> None:
    github.head_repo = "mallory/specs"
    github.add_file(SPEC, DOC)
    assert _run(github, tmp_path).reviewed == 1
    assert any(r.path == "/repos/acme/specs/pulls/7" for r in github.requests)


def test_a_pull_request_event_does_not_pay_for_the_head_check(github: FakeGitHub) -> None:
    from tests.github.test_runner import _run as run_pr

    github.add_file(SPEC, DOC)
    run_pr(github)
    assert not any(r.path == "/repos/acme/specs/pulls/7" for r in github.requests)
