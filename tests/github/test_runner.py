"""PB35-p1: the whole action against a fake GitHub and a scripted provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from probative.critique.pipeline import CritiqueOptions
from probative.interfaces.github.api import GitHubClient
from probative.interfaces.github.context import load_context
from probative.interfaces.github.review import SUMMARY_MARKER
from probative.interfaces.github.runner import ActionOptions, RunResult, run_review
from tests.critique._sample import DOC
from tests.critique._scripted import Scripted
from tests.github.conftest import EVENTS, HEAD_SHA, FakeGitHub

TOKEN = "ghs_secret_token_value_123"
SPEC = "specs/checkout-prd.md"


def _opts(**kwargs: object) -> ActionOptions:
    return ActionOptions(**kwargs)  # type: ignore[arg-type]


def _run(
    github: FakeGitHub,
    *,
    event: str = "pull_request_same_repo.json",
    event_name: str = "pull_request",
    options: ActionOptions | None = None,
    provider: object | None = None,
    clock: object | None = None,
) -> RunResult:
    return run_review(
        load_context(EVENTS / event, event_name),
        GitHubClient(github.url, TOKEN),
        options or _opts(),
        provider=provider or Scripted(),  # type: ignore[arg-type]
        critique_options=CritiqueOptions(model="test/model", jobs=2, clock=lambda: 0.0),
        clock=clock or (lambda: 0.0),  # type: ignore[arg-type]
    )


def test_a_spec_pr_gets_an_inline_review_and_a_summary(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    result = _run(github)
    assert result.exit_code == 0
    review = github.reviews()[0].body
    assert review["event"] == "COMMENT" and review["commit_id"] == HEAD_SHA
    assert {c["path"] for c in review["comments"]} == {SPEC}
    assert len(github.issue_comments) == 1
    assert SUMMARY_MARKER in github.issue_comments[0]["body"]
    assert result.inline_posted == len(review["comments"]) > 0


def test_every_file_is_read_at_the_event_sha_and_nothing_is_checked_out(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    _run(github)
    reads = [r for r in github.requests if "/contents/" in r.path]
    assert reads and all(r.query["ref"] == [HEAD_SHA] for r in reads)


def test_a_rerun_with_the_same_findings_posts_no_new_comments(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    _run(github)
    inline = len(github.review_comments)
    github.reset_log()
    result = _run(github, event="pull_request_synchronize.json")
    assert github.reviews() == []
    assert len(github.review_comments) == inline
    assert len(github.issue_comments) == 1
    assert not [r for r in github.writes() if r.method == "POST"]
    assert result.inline_posted == 0


def test_a_new_finding_adds_only_itself(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    _run(github)
    before = len(github.review_comments)
    github.files.clear()
    github.add_file(SPEC, DOC + "NEED: Users need a FLAG second dashboard.\n")
    _run(github, event="pull_request_synchronize.json")
    assert len(github.review_comments) == before + 1
    assert len(github.issue_comments) == 1


def test_a_rejected_review_falls_back_to_the_summary(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    github.reject_review_with_422 = True
    result = _run(github)
    assert result.exit_code == 0
    assert github.review_comments == []
    assert "GitHub rejected the inline comment" in github.issue_comments[0]["body"]


def test_a_fork_pr_posts_and_fetches_nothing(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    result = _run(github, event="pull_request_fork.json")
    assert result.exit_code == 0
    assert github.requests == []
    assert any("fork" in m for m in result.messages)


def test_pull_request_target_is_refused_in_p1(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    result = _run(github, event_name="pull_request_target")
    assert github.requests == [] and result.exit_code == 0


def test_a_pr_with_no_spec_files_writes_nothing(github: FakeGitHub) -> None:
    github.add_file("src/app.py", "print(1)\n")
    result = _run(github)
    assert github.writes() == []
    assert result.exit_code == 0


def test_removed_files_are_not_read(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC, status="removed", patch=None)
    _run(github)
    assert not [r for r in github.requests if "/contents/" in r.path]
    assert github.writes() == []


def test_paths_globs_select_files(github: FakeGitHub) -> None:
    github.add_file("specs/a.md", DOC)
    github.add_file("README.md", DOC.replace("12%", "13%"))
    _run(github, options=_opts(paths=("specs/**",)))
    reads = {r.path.split("/contents/")[1] for r in github.requests if "/contents/" in r.path}
    assert reads == {"specs/a.md"}


def test_the_file_cap_lists_the_overflow_as_skipped(github: FakeGitHub) -> None:
    for name in ("a", "b", "c"):
        github.add_file(f"specs/{name}.md", DOC.replace("12%", f"1{ord(name)}%"))
    result = _run(github, options=_opts(max_files=2))
    body = github.issue_comments[0]["body"]
    assert "specs/c.md" in body and "over the file cap of 2" in body
    assert len(result.skipped) == 1


def test_the_time_budget_stops_before_the_next_file(github: FakeGitHub) -> None:
    for name in ("a", "b"):
        github.add_file(f"specs/{name}.md", DOC.replace("12%", f"1{ord(name)}%"))
    ticks = iter([0, 0] + [600] * 50)  # the second file is checked ten minutes in
    result = _run(github, options=_opts(max_minutes=5.0), clock=lambda: float(next(ticks)))
    body = github.issue_comments[0]["body"]
    assert "specs/b.md" in body and "time budget" in body
    assert len(result.skipped) == 1


def test_a_pdf_is_summary_only(github: FakeGitHub) -> None:
    pdf = Path(__file__).resolve().parent.parent / "fixtures" / "ingest" / "memo.pdf"
    github.add_file("specs/memo.pdf", pdf.read_bytes(), patch=None)
    result = _run(github)
    assert result.exit_code == 0
    assert github.reviews() == []
    assert "specs/memo.pdf" in github.issue_comments[0]["body"]


def test_unreadable_text_is_skipped_with_a_reason(github: FakeGitHub) -> None:
    github.add_file("specs/bad.md", b"\xff\xfe not utf8 \x80\x81", patch=None)
    result = _run(github)
    assert result.exit_code == 0
    assert "specs/bad.md" in github.issue_comments[0]["body"]


def test_fail_on_never_ignores_block_findings(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    assert _run(github, options=_opts(fail_on="never")).exit_code == 0


def test_fail_on_block_fails_on_a_block_finding(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    assert _run(github, options=_opts(fail_on="block")).exit_code == 1


def test_fail_on_block_passes_a_clean_file(github: FakeGitHub) -> None:
    github.add_file(SPEC, "# Notes\n\nNEED: Users want to pay without retyping details.\n")
    assert _run(github, options=_opts(fail_on="block")).exit_code == 0


class _Leaky(Scripted):
    def complete_structured(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError("401 bad key sk-ant-SECRET123")


@pytest.mark.parametrize(("fail_on", "code"), [("never", 0), ("block", 2)])
def test_a_provider_failure_never_leaks_and_follows_fail_on(
    github: FakeGitHub, fail_on: str, code: int
) -> None:
    github.add_file(SPEC, DOC)
    result = _run(github, options=_opts(fail_on=fail_on), provider=_Leaky())
    assert result.exit_code == code
    everything = repr([r.body for r in github.requests]) + "\n".join(result.messages)
    assert "sk-ant-SECRET123" not in everything
    assert TOKEN not in everything


def test_the_token_is_never_in_a_posted_body(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    _run(github)
    assert TOKEN not in repr([r.body for r in github.requests])


def test_a_github_failure_when_listing_files_follows_fail_on(github: FakeGitHub) -> None:
    github.fail_files_with = 500
    result = _run(github, options=_opts(fail_on="block"))
    assert result.exit_code == 2
    assert TOKEN not in "\n".join(result.messages)
    assert _run(github, options=_opts(fail_on="never")).exit_code == 0


def test_a_foreign_summary_comment_is_never_overwritten(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    github.issue_comments.append(
        {
            "id": 5,
            "user": {"login": "copilot-pull-request-reviewer[bot]"},
            "body": f"{SUMMARY_MARKER} quoted",
        }
    )
    _run(github)
    assert github.issue_comments[0]["body"] == f"{SUMMARY_MARKER} quoted"
    assert len(github.issue_comments) == 2


def test_the_summary_survives_a_failed_review_post(github: FakeGitHub) -> None:
    github.add_file(SPEC, DOC)
    github.reject_review_with = 403
    result = _run(github)
    assert result.exit_code == 0
    assert "GitHub rejected the inline comment" in github.issue_comments[0]["body"]
    assert any(m.startswith("::warning::") for m in result.messages)


def test_block_mode_does_not_pass_a_run_that_skipped_files(github: FakeGitHub) -> None:
    for name in ("a", "b"):
        github.add_file(f"specs/{name}.md", "# Notes\n\nNEED: Users want to pay.\n" + name)
    assert _run(github, options=_opts(fail_on="block", max_files=1)).exit_code == 1


def test_a_workflow_command_cannot_be_forged_from_an_error_message(github: FakeGitHub) -> None:
    github.fail_files_with = 500
    github.error_message = "bad\n::add-mask::hello\n100%"
    result = _run(github)
    for message in result.messages:
        assert "\n" not in message and "\r" not in message
    assert not any(
        line.startswith("::add-mask::") for m in result.messages for line in m.split("\n")
    )
