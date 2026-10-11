"""The action, end to end (PB35-p1): decide, list, read, critique, plan, post.

Every network call goes through `GitHubClient`; the model is whatever `Provider` the caller
hands in. Nothing here checks out or runs PR code: each file is fetched at the event's head
SHA into a temp directory and read by the same `critique()` the CLI uses. A failure on one
file is that file's skip reason, never a lost run.
"""

from __future__ import annotations

import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from probative.critique import NoReadableInputError
from probative.critique import critique as run_critique
from probative.critique.pipeline import CritiqueOptions
from probative.critique.report import SkippedFile
from probative.interfaces.github.anchor import normalise
from probative.interfaces.github.api import ChangedFile, GitHubClient, GitHubError
from probative.interfaces.github.context import PullRequestContext
from probative.interfaces.github.patch import parse_patch
from probative.interfaces.github.review import (
    BOT_LOGIN,
    SUMMARY_MARKER,
    FileOutcome,
    ReviewPlan,
    existing_markers,
    plan_review,
)
from probative.interfaces.github.trust import DEFAULT_LABEL, TrustDecision
from probative.llm import Provider

DEFAULT_PATHS = ("**/*.md", "**/*.markdown", "**/*.txt", "**/*.pdf", "**/*.docx", "**/*.xlsx")
_LINE_ADDRESSABLE = {".md", ".markdown", ".txt"}
# What an author without write access may have critiqued: no PDF, DOCX or XLSX parser ever
# runs over their bytes while the model key is in the environment.
UNTRUSTED_FORMATS = (".md", ".markdown", ".txt")
MAX_UNTRUSTED_BYTES = 1024 * 1024
_RESTRICTED = "format not allowed for authors without write access (text files only)"


@dataclass(frozen=True)
class ActionOptions:
    paths: tuple[str, ...] = DEFAULT_PATHS
    max_files: int = 25
    max_minutes: float = 20.0
    fail_on: Literal["never", "block"] = "never"
    max_inline: int = 50
    label: str = DEFAULT_LABEL


@dataclass
class RunResult:
    exit_code: int = 0
    messages: list[str] = field(default_factory=list)
    inline_posted: int = 0
    reviewed: int = 0
    skipped: list[SkippedFile] = field(default_factory=list)


def annotate(level: str, text: str) -> str:
    """A workflow command with its data escaped the way the runner reads it, so text from an
    API response or a file name cannot end the line and start another command."""
    data = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::{level}::{data}"


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**/` spans directories, `*` and `?` stay inside one path segment."""
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _matches(path: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.match(path) for p in patterns)


def _suffix(path: str) -> str:
    return PurePosixPath(path).suffix.lower()


def _skip(path: str, reason: str) -> SkippedFile:
    return SkippedFile(path=path, reason=reason)


def run_review(
    ctx: PullRequestContext,
    decision: TrustDecision,
    client: GitHubClient,
    options: ActionOptions,
    *,
    provider: Provider,
    critique_options: CritiqueOptions,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    result = RunResult()
    if not decision.allowed:
        result.messages.append(annotate("notice", decision.reason))
        return result
    errored = False

    def failed(message: str) -> RunResult:
        result.messages.append(annotate("warning", message))
        result.exit_code = 2 if options.fail_on == "block" else 0
        return result

    if ctx.event_name == "pull_request_target":
        # the label (or push) event names a commit; if the PR moved on, what was approved is
        # not what the file list and the patches now describe
        try:
            current = client.pr_head_sha(ctx.repo, ctx.number)
        except GitHubError as error:
            return failed(f"could not check the pull request's head: {error}")
        if current != ctx.head_sha:
            result.messages.append(
                annotate(
                    "notice", "the pull request head moved since this event; nothing was reviewed"
                )
            )
            return result
    try:
        changed = client.list_pr_files(ctx.repo, ctx.number)
    except GitHubError as error:
        return failed(f"could not list the pull request's files: {error}")

    patterns = tuple(glob_to_regex(p) for p in options.paths)
    matched = sorted(
        (f for f in changed if f.status != "removed" and _matches(f.path, patterns)),
        key=lambda f: f.path,
    )
    wanted = matched
    if decision.restrict_formats:
        wanted = [f for f in matched if _suffix(f.path) in UNTRUSTED_FORMATS]
        result.skipped += [_skip(f.path, _RESTRICTED) for f in matched if f not in wanted]
    if not wanted:
        what = "no changed file matches the paths to critique"
        if result.skipped:
            what = f"{len(result.skipped)} changed file(s) skipped: {_RESTRICTED}"
        result.messages.append(annotate("notice", what))
        return result
    chosen, over = wanted[: options.max_files], wanted[options.max_files :]
    result.skipped += [_skip(f.path, f"over the file cap of {options.max_files}") for f in over]

    outcomes: list[FileOutcome] = []
    started = clock()
    with tempfile.TemporaryDirectory(prefix="probative-gh-") as work:
        for index, file in enumerate(chosen):
            if (clock() - started) / 60.0 >= options.max_minutes:
                result.skipped += [
                    _skip(f.path, f"time budget of {options.max_minutes:g} minutes used up")
                    for f in chosen[index:]
                ]
                break
            try:
                outcome = _critique_one(
                    client,
                    ctx,
                    file,
                    Path(work) / str(index),
                    provider,
                    critique_options,
                    restrict_formats=decision.restrict_formats,
                )
            except _FileSkipped as skip:
                result.skipped.append(_skip(file.path, skip.reason))
                errored = errored or skip.is_error
                continue
            outcomes.append(outcome)
    result.reviewed = len(outcomes)

    try:
        post_error = _post(ctx, client, options, outcomes, result)
    except GitHubError as error:
        return failed(f"could not post the summary: {error}")
    if post_error is not None:
        failed(f"could not post the inline review: {post_error}")
        errored = True

    if options.fail_on == "block":
        # a file that was not critiqued (cap, budget, unreadable) could hold the blocker
        blocked = any(o.report.totals.block or o.report.incomplete for o in outcomes)
        result.exit_code = 2 if errored else (1 if blocked or result.skipped else 0)
    if errored:
        result.messages.append(
            annotate("warning", "some files could not be critiqued or posted; see the summary")
        )
    return result


class _FileSkipped(Exception):
    def __init__(self, reason: str, *, is_error: bool = False) -> None:
        self.reason = reason
        self.is_error = is_error
        super().__init__(reason)


def _critique_one(
    client: GitHubClient,
    ctx: PullRequestContext,
    file: ChangedFile,
    workdir: Path,
    provider: Provider,
    options: CritiqueOptions,
    *,
    restrict_formats: bool = False,
) -> FileOutcome:
    # the gate is here as well as in the file list: nothing is downloaded, let alone parsed
    if restrict_formats and _suffix(file.path) not in UNTRUSTED_FORMATS:
        raise _FileSkipped(_RESTRICTED)
    try:
        raw = client.get_file(ctx.head_repo or ctx.repo, file.path, ctx.head_sha)
    except GitHubError as error:
        raise _FileSkipped(f"could not be read (HTTP {error.status})", is_error=True) from None
    if restrict_formats and len(raw) > MAX_UNTRUSTED_BYTES:
        raise _FileSkipped("over the 1 MB size cap for outside authors")
    suffix = _suffix(file.path)
    addressable = suffix in _LINE_ADDRESSABLE
    text = ""
    if addressable:
        try:
            text = normalise(raw.decode("utf-8"))
        except UnicodeDecodeError:
            raise _FileSkipped("not valid UTF-8 text") from None
    workdir.mkdir(parents=True)
    target = workdir / PurePosixPath(file.path).name
    target.write_bytes(raw)
    try:
        run = run_critique(target, provider, options)
    except NoReadableInputError as error:
        raise _FileSkipped(_first_reason(error)) from None
    except Exception as error:  # a provider outage, a bug: name the class, never the text
        raise _FileSkipped(f"critique failed ({type(error).__name__})", is_error=True) from None
    patch = parse_patch(file.patch) if file.patch is not None else None
    return FileOutcome(file.path, run.report, text, patch, addressable)


def _first_reason(error: NoReadableInputError) -> str:
    return error.skipped[0].reason if error.skipped else "no readable document"


def _post(
    ctx: PullRequestContext,
    client: GitHubClient,
    options: ActionOptions,
    outcomes: list[FileOutcome],
    result: RunResult,
) -> GitHubError | None:
    """Post the review, then the summary. A failed review never costs the summary: the
    findings move into it. Returns the error when the review failed for a reason other than
    GitHub refusing a comment's position (422)."""
    review_error: GitHubError | None = None
    posted = client.list_review_comments(ctx.repo, ctx.number)
    existing = existing_markers(posted)
    plan = plan_review(outcomes, result.skipped, existing=existing, max_inline=options.max_inline)
    if plan.comments:
        payload = [
            {
                "path": c.path,
                "line": c.line,
                "side": c.side,
                "body": c.body,
                **({"start_line": c.start_line, "start_side": c.side} if c.start_line else {}),
            }
            for c in plan.comments
        ]
        try:
            client.create_review(ctx.repo, ctx.number, ctx.head_sha, payload)
            result.inline_posted = len(plan.comments)
        except GitHubError as error:
            if error.status != 422:
                review_error = error
            plan = plan_review(
                outcomes,
                result.skipped,
                existing=existing,
                max_inline=0,
                overflow="inline_rejected",
            )
    _upsert_summary(ctx, client, plan)
    return review_error


def _upsert_summary(ctx: PullRequestContext, client: GitHubClient, plan: ReviewPlan) -> None:
    for comment in client.list_issue_comments(ctx.repo, ctx.number):
        login = str((comment.get("user") or {}).get("login", ""))
        if login == BOT_LOGIN and str(comment.get("body", "")).startswith(SUMMARY_MARKER):
            if comment.get("body") != plan.summary_body:
                client.update_issue_comment(ctx.repo, int(comment["id"]), plan.summary_body)
            return
    client.create_issue_comment(ctx.repo, ctx.number, plan.summary_body)
