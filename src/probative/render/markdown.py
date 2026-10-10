"""Markdown projection of a `CritiqueReport` (PB9, I5).

A pure function of the report: no free-text slot, no model call. Quotes are
untrusted document text, so every dynamic string is backslash-escaped and its
whitespace collapsed before it reaches Markdown.
"""

from __future__ import annotations

import re

from probative.critique.report import CritiqueReport, DimensionStatus
from probative.render._view import (
    SEVERITY_LABEL,
    SEVERITY_ORDER,
    clean_cell,
    finding_groups,
    floor_cell,
    group_total,
    reply_label,
    run_line,
    skipped_line,
    status_text,
    totals_line,
)

_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+!|~&$])")
_AUTOLINK = re.compile(r"(?i)\b((?:https?|ftp):|www)(//|\.)")


def md(text: str) -> str:
    """Collapse whitespace and escape everything Markdown or HTML could act on."""
    flat = " ".join(text.split())
    # break bare-URL autolinks (GFM) without touching the visible characters
    flat = _AUTOLINK.sub(lambda m: m.group(1) + "\u200b" + m.group(2), flat)
    escaped = _SPECIAL.sub(r"\\\1", flat)
    return escaped.replace("-", "\\-") if flat.startswith("-") else escaped


def render_summary(report: CritiqueReport) -> str:
    """The headline block: what the terminal prints."""
    skipped = skipped_line(report)
    lines = [
        f"# Probative critique: {md(report.subject)}",
        "",
        md(run_line(report)),
        "",
        f"**{totals_line(report)}**",
        "",
        *([md(skipped), ""] if skipped else []),
        "| Dimension | Checked | Clean | Block | Warn | Note | Floor (0 to 10) | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for dim in report.dimensions:
        lines.append(
            f"| {md(dim.label)} | {dim.checked} | {clean_cell(dim)} | {dim.counts.block} "
            f"| {dim.counts.warn} | {dim.counts.note} | {floor_cell(dim)} | {status_text(dim)} |"
        )
    return "\n".join(lines) + "\n"


def render_markdown(report: CritiqueReport) -> str:
    out = [render_summary(report)]

    groups = finding_groups(report)
    out.append("## Findings\n")
    if not groups:
        out.append("No findings.\n")
    for severity in SEVERITY_ORDER:
        mine = [g for g in groups if g.severity is severity]
        if not mine:
            continue
        out.append(f"### {SEVERITY_LABEL[severity]}\n")
        for group in mine:
            out.append(
                f"#### {md(group.dimension.label)}: {md(group.headline)} {group_total(group)}\n"
            )
            for f in group.findings:
                # the quote is alone in its block: nothing the rubric wrote may sit inside it
                out.append(f"> “{md(f.quote)}”")
                out.append("")
                out.append(f"{md(_doc_name(report, f.source_id))}, {md(f.locator_label)}\\")
                if f.detail:
                    out.append(f"{md(f.detail)}\\")
                out.append(f"Fix: {md(f.remedy)}")
                out.append("")

    unassessed = [d for d in report.dimensions if d.status is not DimensionStatus.ASSESSED]
    out.append("## Not assessed\n")
    if not unassessed:
        out.append("Every dimension was assessed.\n")
    for dim in unassessed:
        out.append(f"- {md(dim.label)}: {status_text(dim)}")
    if unassessed:
        out.append("")

    out.append("## Coverage\n")
    kinds = sorted({k for d in report.documents for k in d.candidates})
    out.append("| Document | Format | " + " | ".join(kinds) + " |")
    out.append("|---|---|" + "---:|" * len(kinds))
    for doc in report.documents:
        counts = " | ".join(str(doc.candidates.get(k, 0)) for k in kinds)
        out.append(f"| {md(doc.file_name)} | {doc.format.value} ({doc.format_choice}) | {counts} |")
    out.append("")
    rejected = [(d.file_name, d.rejected) for d in report.documents if d.rejected]
    for name, reasons in rejected:
        detail = ", ".join(f"{k} {v}" for k, v in reasons.items())
        out.append(f"- Quotes the model proposed that were not found: {md(name)}: {detail}")
    if report.skipped:
        out.append("\nSkipped:\n")
        out.extend(f"- {md(s.path)}: {md(s.reason)}" for s in report.skipped)
    r = report.run
    out.append(
        f"\n{r.input_tokens} input tokens · {r.output_tokens} output tokens · "
        f"{r.jobs} concurrent calls · {md(reply_label(report))} · "
        f"probative {md(report.tool_version)}\n"
    )
    return "\n".join(out)


def _doc_name(report: CritiqueReport, source_id: str) -> str:
    return next(d.file_name for d in report.documents if d.source_id == source_id)
