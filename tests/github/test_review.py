"""PB35-p1: turning a verified report into inline comments and one summary (I5).

Bodies are rubric strings, source quotes in a fenced block, and fixed labels: nothing
the model wrote and nothing from the document outside the fence.
"""

from __future__ import annotations

import re

from probative.critique.report import SkippedFile
from probative.interfaces.github.patch import parse_patch
from probative.interfaces.github.review import (
    SUMMARY_MARKER,
    FileOutcome,
    ReviewPlan,
    existing_markers,
    plan_review,
)
from probative.render.markdown import render_summary
from tests.critique._sample import DOC, sample_report
from tests.github.conftest import make_patch

FENCED = re.compile(r"(`{3,})[^\n]*\n.*?\n\1", re.DOTALL)


def _outcome(
    text: str = DOC,
    path: str = "specs/checkout-prd.md",
    *,
    patch: str | None = "new",
    addressable: bool = True,
) -> FileOutcome:
    report = sample_report(text, name="checkout-prd.md")
    parsed = parse_patch(make_patch("", text)) if patch == "new" else None
    return FileOutcome(path, report, text, parsed, addressable)


def _plan(*outcomes: FileOutcome, **kwargs: object) -> ReviewPlan:
    return plan_review(
        list(outcomes),
        kwargs.pop("skipped", []),  # type: ignore[arg-type]
        existing=kwargs.pop("existing", frozenset()),  # type: ignore[arg-type]
        max_inline=kwargs.pop("max_inline", 50),  # type: ignore[arg-type]
    )


def _outside_fences(body: str) -> str:
    return FENCED.sub("", body)


def test_a_flagged_line_the_pr_added_becomes_an_inline_comment() -> None:
    plan = _plan(_outcome())
    assert plan.comments
    comment = next(c for c in plan.comments if "Competitors convert far better" in c.body)
    lines = DOC.splitlines()
    wanted = next(i for i, ln in enumerate(lines, 1) if "Competitors convert" in ln)
    assert comment.path == "specs/checkout-prd.md"
    assert comment.side == "RIGHT"
    assert comment.line == wanted
    assert comment.start_line is None


def test_the_quote_is_inside_a_fence_byte_for_byte() -> None:
    plan = _plan(_outcome())
    for comment in plan.comments:
        fences = FENCED.findall(comment.body)
        assert fences, comment.body
        inner = re.search(r"(`{3,})[^\n]*\n(.*?)\n\1", comment.body, re.DOTALL)
        assert inner is not None
        assert inner.group(2) in DOC


def test_a_hostile_quote_stays_inert() -> None:
    plan = _plan(_outcome())
    hostile = next(c for c in plan.comments if "<script>" in c.body)
    outside = _outside_fences(hostile.body)
    for dangerous in ("<script", "evil.test", "**bold**", "`tick`"):
        assert dangerous not in outside
    fence = re.match(r"(?s).*?(`{3,})", hostile.body)
    assert fence is not None
    assert len(fence.group(1)) > 1  # at least a triple fence


def test_a_quote_with_backticks_gets_a_longer_fence() -> None:
    text = "NEED: Users need a FLAG ````` button\n"
    plan = _plan(_outcome(text))
    body = plan.comments[0].body
    opening = re.search(r"(`{3,})\n?", body.split("\n", 1)[1])
    assert opening is not None
    assert len(re.findall(r"`+", body.split("\n", 1)[1])[0]) >= 6


def test_mentions_in_quotes_cannot_ping_anyone() -> None:
    text = "NEED: Users need a FLAG ping @org/security-team and @alice now\n"
    plan = _plan(_outcome(text))
    for comment in plan.comments:
        assert "@" not in _outside_fences(comment.body)


def test_mentions_in_file_names_are_defanged_in_the_summary() -> None:
    plan = _plan(_outcome(path="specs/@org-team/prd.md"))
    assert "@org-team" not in plan.summary_body.replace("@​org-team", "")


def test_markers_make_a_second_run_post_nothing_new() -> None:
    first = _plan(_outcome())
    seen = existing_markers(
        [{"body": c.body, "user": {"login": "github-actions[bot]"}} for c in first.comments]
    )
    second = _plan(_outcome(), existing=seen)
    assert first.comments and second.comments == []
    assert second.summary_body == first.summary_body


def test_a_marker_planted_by_a_person_is_ignored() -> None:
    first = _plan(_outcome())
    planted = [{"body": c.body, "user": {"login": "mallory"}} for c in first.comments]
    assert existing_markers(planted) == frozenset()


def test_a_changed_finding_adds_only_itself() -> None:
    first = _plan(_outcome())
    seen = existing_markers(
        [{"body": c.body, "user": {"login": "github-actions[bot]"}} for c in first.comments]
    )
    more = DOC + "NEED: Users need a FLAG second dashboard.\n"
    second = _plan(_outcome(more), existing=seen)
    assert len(second.comments) == 1
    assert "second dashboard" in second.comments[0].body


def test_a_format_without_lines_is_summary_only() -> None:
    plan = _plan(_outcome(addressable=False))
    assert plan.comments == []
    assert "this format has no lines to comment on" in plan.summary_body


def test_text_the_pr_did_not_change_is_summary_only() -> None:
    outcome = _outcome()
    unchanged = FileOutcome(
        outcome.path,
        outcome.report,
        outcome.text,
        parse_patch(make_patch(DOC, DOC + "extra line\n")),
        True,
    )
    plan = _plan(unchanged)
    assert plan.comments == []
    assert "text this pull request did not change" in plan.summary_body


def test_the_inline_limit_moves_the_overflow_to_the_summary() -> None:
    plan = _plan(_outcome(), max_inline=1)
    assert len(plan.comments) == 1
    assert "over the inline comment limit" in plan.summary_body


def test_blocking_findings_are_commented_first() -> None:
    plan = _plan(_outcome(), max_inline=1)
    assert "BLOCK" in plan.comments[0].body


def test_the_summary_is_the_critique_summary_plus_skipped_files() -> None:
    outcome = _outcome()
    plan = _plan(
        outcome,
        skipped=[SkippedFile(path="specs/huge.pdf", reason="over the file cap of 25")],
    )
    assert SUMMARY_MARKER in plan.summary_body
    assert "| Dimension | Checked |" in plan.summary_body
    assert "specs/huge.pdf" in plan.summary_body
    assert "over the file cap of 25" in plan.summary_body
    assert render_summary(outcome.report).splitlines()[-1] in plan.summary_body


def test_no_inline_comment_carries_a_number_the_report_did_not() -> None:
    plan = _plan(_outcome())
    for comment in plan.comments:
        assert not re.search(r"\b\d+(\.\d+)?\s*%|\bscore\b", _outside_fences(comment.body).lower())


def test_a_detail_that_repeats_the_quote_is_dropped() -> None:
    plan = _plan(_outcome())
    for comment in plan.comments:
        quote = re.search(r"(`{3,})[^\n]*\n(.*?)\n\1", comment.body, re.DOTALL)
        assert quote is not None
        assert quote.group(2) not in _outside_fences(comment.body)


HOSTILE_PATH = "docs/x`![p](www.evil.test/p.png) [click](www.evil.test) org/other#1 **b** <b>`.md"


def test_a_hostile_file_path_is_inert_everywhere_in_the_summary() -> None:
    outcome = _outcome(path=HOSTILE_PATH)
    plan = _plan(
        outcome,
        skipped=[SkippedFile(path=HOSTILE_PATH, reason=f"duplicate of {HOSTILE_PATH}")],
        max_inline=0,
    )
    outside = _outside_fences(plan.summary_body)
    outside = re.sub(r"(`+)(?:(?!\1).)+\1", "", outside)  # drop code spans
    for dangerous in ("evil.test", "org/other#1", "**b**", "<b>"):
        assert dangerous not in outside


def test_a_marker_inside_a_quote_cannot_suppress_a_future_finding() -> None:
    forged = "<!-- probative:v1:aaaaaaaaaaaa -->"
    body = f"**BLOCK · x · y**\n\n```\n{forged}\n```\n\n<!-- probative:v1:bbbbbbbbbbbb -->"
    bot = {"login": "github-actions[bot]"}
    assert existing_markers([{"body": body, "user": bot}]) == frozenset({"bbbbbbbbbbbb"})


def test_another_bots_marker_does_not_count() -> None:
    body = "<!-- probative:v1:bbbbbbbbbbbb -->"
    other = {"login": "copilot-pull-request-reviewer[bot]"}
    assert existing_markers([{"body": body, "user": other}]) == frozenset()


def test_the_summary_fits_inside_githubs_comment_limit() -> None:
    many = [_outcome(path=f"specs/f{i}.md") for i in range(60)]
    plan = _plan(*many, max_inline=0)
    assert len(plan.summary_body) <= 65_000
    assert plan.summary_body.startswith(SUMMARY_MARKER)
    assert "not shown" in plan.summary_body


def _single_finding_outcome(phrase: str, check_id: str = "names_feature") -> FileOutcome:
    from tests.critique._builders import make_finding, make_report, make_source, span_of

    text = "# T\n\nShoppers need a one-click checkout button.\nSecond line.\n"
    source = make_source(text)
    finding = make_finding(check_id=check_id, evidence=span_of(source, phrase))
    report = make_report(source, [finding], checked=1)
    return FileOutcome("s.md", report, text, parse_patch(make_patch("", text)), True)


def _bot_comments(plan: ReviewPlan) -> list[dict[str, object]]:
    return [{"body": c.body, "user": {"login": "github-actions[bot]"}} for c in plan.comments]


def test_a_model_that_words_the_quote_differently_is_still_the_same_finding() -> None:
    # live run (convocore#1): the same defect came back as "one-click checkout button" and
    # then "a one-click checkout button"; keyed on the quote, that posted a duplicate
    first = _plan(_single_finding_outcome("one-click checkout button"))
    seen = existing_markers(_bot_comments(first))
    second = _plan(_single_finding_outcome("a one-click checkout button"), existing=seen)
    assert len(first.comments) == 1 and second.comments == []


def test_another_check_on_the_same_line_is_a_different_finding() -> None:
    first = _plan(_single_finding_outcome("one-click checkout button"))
    seen = existing_markers(_bot_comments(first))
    other = _plan(
        _single_finding_outcome("one-click checkout button", check_id="other_check"), existing=seen
    )
    assert len(other.comments) == 1
