"""A verified report, planned as a PR review (PB35, I5).

Pure: no network, no clock. Every string is a rubric string, a fixed label, or a source
quote inside a code fence. A fence is the one place GitHub neither pings an @mention nor
autolinks a URL, so hostile document text stays inert, and the quote is still the file's
own bytes (I1). Inline comments go only where the PR wrote the line; the rest, with the
reason, is in the summary. Nothing is deleted on a rerun: a finding is posted once, keyed by
a marker, and the summary is rewritten in place.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from probative import __version__
from probative.core.critic import Severity
from probative.critique.report import CritiqueReport, ReportFinding, SkippedFile
from probative.interfaces.github.anchor import Anchor, anchor_quote
from probative.interfaces.github.patch import PatchMap
from probative.render._view import SEVERITY_ORDER, SEVERITY_WORD
from probative.render.markdown import md, render_summary

SUMMARY_MARKER = "<!-- probative:summary -->"
_MARKER = re.compile(r"<!-- probative:v1:([0-9a-f]{12}) -->")
BOT_LOGIN = "github-actions[bot]"
MAX_SUMMARY_CHARS = 60_000  # GitHub rejects a comment body over 65,536
_FENCED = re.compile(r"(`{3,})[^\n]*\n.*?\n\1", re.DOTALL)
_REASON_LABEL = {
    "ambiguous_quote": "the quote appears more than once in the file",
    "quote_not_found": "the quote was not found in the file text",
    "unchanged_text": "text this pull request did not change",
    "no_patch": "GitHub sent no diff for this file",
    "not_line_addressable": "this format has no lines to comment on",
    "inline_limit": "over the inline comment limit",
    "inline_rejected": "GitHub rejected the inline comment",
}


class ReviewComment(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    line: int
    start_line: int | None = None
    side: str = "RIGHT"
    body: str
    marker: str


class ReviewPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    comments: list[ReviewComment]
    summary_body: str
    summary_only: int = 0
    already_posted: int = 0


@dataclass(frozen=True)
class FileOutcome:
    path: str
    report: CritiqueReport
    text: str  # the file, normalised the way the ingester normalises it
    patch: PatchMap | None
    line_addressable: bool


def defang(text: str) -> str:
    """Stop `@name` from mentioning anyone, without changing what is shown."""
    return text.replace("@", "@​")


def code_span(text: str) -> str:
    """Text as an inline code span that no backtick inside it can close."""
    flat = defang(" ".join(text.split()))
    longest = max((len(run) for run in re.findall(r"`+", flat)), default=0)
    ticks = "`" * (longest + 1)
    pad = " " if flat.startswith("`") or flat.endswith("`") else ""
    return f"{ticks}{pad}{flat}{pad}{ticks}"


def fence(text: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}\n{text}\n{ticks}"


def marker_id(path: str, check_id: str, line_text: str) -> str:
    """Keyed on the file's own line(s), not on the model's quote: a model asked again picks
    a slightly different span of the same sentence (seen live), and that is not a new finding."""
    return hashlib.sha256(f"{path}\0{check_id}\0{line_text}".encode()).hexdigest()[:12]


def existing_markers(comments: Iterable[Mapping[str, Any]]) -> frozenset[str]:
    """Marker ids already on the PR. Only this action's own comments count (a person or
    another bot cannot suppress a finding by pasting its marker), and a marker inside a
    quoted block is document text, not ours."""
    found: set[str] = set()
    for comment in comments:
        user = comment.get("user") or {}
        if str(user.get("login", "")) != BOT_LOGIN:
            continue
        found.update(_MARKER.findall(_FENCED.sub("", str(comment.get("body", "")))))
    return frozenset(found)


def _body(finding: ReportFinding, dimension_label: str, marker: str) -> str:
    word = SEVERITY_WORD[finding.severity]
    head = f"**{word} · {dimension_label} · {defang(finding.check_headline)}**"
    parts = [head, "", fence(finding.quote)]
    if finding.detail and finding.quote not in finding.detail:
        parts += ["", defang(finding.detail)]
    if finding.remedy:
        parts += ["", f"Remedy: {defang(finding.remedy)}"]
    parts += ["", f"<!-- probative:v1:{marker} -->"]
    return "\n".join(parts)


@dataclass(frozen=True)
class _Row:
    outcome: FileOutcome
    finding: ReportFinding
    dimension: str
    anchor: Anchor


def _rows(outcome: FileOutcome) -> list[_Row]:
    rows: list[_Row] = []
    for dim in outcome.report.dimensions:
        for finding in dim.findings:
            if not outcome.line_addressable:
                anchor = Anchor(kind="summary", reason="not_line_addressable")
            else:
                anchor = anchor_quote(finding.quote, outcome.text, outcome.patch)
            rows.append(_Row(outcome, finding, dim.label, anchor))
    return rows


def _order(row: _Row) -> tuple[int, str, int]:
    return (
        SEVERITY_ORDER.index(row.finding.severity),
        row.outcome.path,
        row.finding.start,
    )


def plan_review(
    outcomes: Sequence[FileOutcome],
    skipped: Sequence[SkippedFile],
    *,
    existing: frozenset[str],
    max_inline: int,
    overflow: str = "inline_limit",
) -> ReviewPlan:
    rows = sorted((row for o in outcomes for row in _rows(o)), key=_order)
    comments: list[ReviewComment] = []
    summary_only: list[tuple[_Row, str]] = []
    already = 0
    for row in rows:
        reason: str | None = row.anchor.reason
        if row.anchor.kind == "inline":
            start, end = row.anchor.start_line, row.anchor.end_line
            assert start is not None and end is not None
            line_text = "\n".join(row.outcome.text.split("\n")[start - 1 : end])
            marker = marker_id(row.outcome.path, row.finding.check_id, line_text)
            if marker in existing:
                already += 1
                continue
            if len(comments) >= max_inline:
                reason = overflow
            else:
                comments.append(
                    ReviewComment(
                        path=row.outcome.path,
                        line=end,
                        start_line=start if start != end else None,
                        body=_body(row.finding, row.dimension, marker),
                        marker=marker,
                    )
                )
                continue
        assert reason is not None
        summary_only.append((row, reason))
    return ReviewPlan(
        comments=comments,
        summary_body=_summary(outcomes, summary_only, skipped),
        summary_only=len(summary_only),
        already_posted=already,
    )


def _summary(
    outcomes: Sequence[FileOutcome],
    summary_only: Sequence[tuple[_Row, str]],
    skipped: Sequence[SkippedFile],
) -> str:
    """Built from self-contained blocks so the body can be cut at a block boundary, never
    inside a code fence, when it would pass GitHub's size limit."""
    head = [SUMMARY_MARKER, "## Probative critique", ""]
    footer = [
        "---",
        f"Probative {__version__}. Findings are the critics' verdicts on quoted text, "
        "not a judgement of the author.",
    ]
    blocks: list[str] = []
    if not outcomes:
        blocks.append("No file in this pull request was critiqued.\n")
    for outcome in outcomes:
        blocks.append(f"### {code_span(outcome.path)}\n\n{defang(render_summary(outcome.report))}")
    for severity in (Severity.BLOCK, Severity.WARN, Severity.NOTE):
        for row, reason in summary_only:
            if row.finding.severity is not severity:
                continue
            blocks.append(
                f"**{SEVERITY_WORD[severity]} · {code_span(row.outcome.path)} · "
                f"{row.dimension} · {defang(row.finding.check_headline)}** "
                f"({_REASON_LABEL[reason]})\n\n{fence(row.finding.quote)}\n"
            )
    for entry in skipped:
        blocks.append(f"- {code_span(entry.path)}: {md(defang(entry.reason))}")
    shown: list[str] = []
    used = sum(len(line) + 1 for line in head + footer) + 200
    for block in blocks:
        if used + len(block) + 1 > MAX_SUMMARY_CHARS:
            break
        shown.append(block)
        used += len(block) + 1
    hidden = len(blocks) - len(shown)
    body = head + shown
    if hidden:
        body += ["", f"_{hidden} more section(s) not shown to stay under GitHub's comment limit._"]
    body += ["", *footer]
    return "\n".join(body).replace("\x00", "") + "\n"
