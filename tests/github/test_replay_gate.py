"""G-PB35 (offline): the recorded `payments` run, as a PR file, through the whole action.

No key and no network: the model answers come from the committed PB9 recording and GitHub
is the local fake. Every inline comment must sit on the lines that hold its quote.
"""

from __future__ import annotations

import json
import re

from probative.critique.pipeline import CritiqueOptions
from probative.interfaces.github.api import GitHubClient
from probative.interfaces.github.context import load_context
from probative.interfaces.github.runner import ActionOptions, run_review
from probative.llm import LiteLLMProvider
from tests._recording import replay
from tests.critique._cases import FIXTURES, RECORDINGS, rerecord_hint
from tests.github.conftest import EVENTS, FakeGitHub

PRD = FIXTURES / "extract" / "prd_payments.md"
FENCE = re.compile(r"(`{3,})[^\n]*\n(.*?)\n\1", re.DOTALL)


def _run(github: FakeGitHub, event: str) -> None:
    results = json.loads((RECORDINGS / "payments" / "results.json").read_text())
    provider = LiteLLMProvider(
        completion_fn=replay(RECORDINGS / "payments", rerecord_hint("payments"))
    )
    run_review(
        load_context(EVENTS / event, "pull_request"),
        GitHubClient(github.url, "ghs_tok"),
        ActionOptions(),
        provider=provider,
        critique_options=CritiqueOptions(
            model=results["model"],
            jobs=results["jobs"],
            reply=results.get("reply", "full"),
            batch_size=results.get("batch_size", 5),
            window_chars=results.get("window_chars", 10_000),
            clock=lambda: 0.0,
        ),
    )


def test_the_recorded_run_becomes_a_review_whose_quotes_are_the_files_bytes(
    github: FakeGitHub,
) -> None:
    text = PRD.read_text(encoding="utf-8")
    github.add_file("docs/saved-cards.md", text)
    _run(github, "pull_request_same_repo.json")

    comments = github.review_comments
    assert comments, "the recording has findings on added lines"
    lines = text.split("\n")
    for comment in comments:
        quote = FENCE.search(comment["body"])
        assert quote is not None
        first = comment.get("start_line", comment["line"])
        covered = "\n".join(lines[first - 1 : comment["line"]])
        assert quote.group(2) in covered
        assert quote.group(2) in text
    body = github.issue_comments[0]["body"]
    assert "| Dimension | Checked |" in body


def test_a_second_push_changes_nothing_when_nothing_changed(github: FakeGitHub) -> None:
    github.add_file("docs/saved-cards.md", PRD.read_text(encoding="utf-8"))
    _run(github, "pull_request_same_repo.json")
    posted = len(github.review_comments)
    github.reset_log()
    _run(github, "pull_request_synchronize.json")
    assert len(github.review_comments) == posted
    assert github.reviews() == []
    assert len(github.issue_comments) == 1
