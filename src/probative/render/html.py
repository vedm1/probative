"""Single-file HTML projection of a `CritiqueReport` (PB9, S4, I5).

A pure function of the report. Document text is untrusted, so every dynamic
string is `html.escape`d, the page uses no inline event handlers and no style
attributes, and a Content-Security-Policy meta tag allows only the page's own
hash-pinned style and script. There is no external URL anywhere. The one script
is progressive enhancement (theme toggle and filters); with it blocked, every
finding still opens as a native `<details>`.

S4 asks that a clickable element open the evidence drawer: here each finding is
a `<details>` showing the quote in its surrounding source text, and nothing
that cannot be traced to a quote is made interactive.
"""

from __future__ import annotations

import base64
import hashlib
from html import escape

from probative.critique.report import (
    CritiqueReport,
    DimensionResult,
    DimensionStatus,
    ReportFinding,
)
from probative.render._view import (
    SEVERITY_GLYPH,
    SEVERITY_LABEL,
    SEVERITY_ORDER,
    SEVERITY_WORD,
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
from probative.render.design import BASE_CSS

_CSS = (
    BASE_CSS
    + """\
.bar { font-family: ui-monospace, Menlo, monospace; }
.chips { display: flex; flex-wrap: wrap; gap: .5rem; margin: .75rem 0; }
.js-only { display: none; }
.js .js-only { display: flex; }
.group { margin: 0 0 1rem; }
details.finding {
  background: var(--surface); border: 1px solid var(--line); border-left-width: 6px;
  border-radius: .3rem; margin: .4rem 0; padding: .1rem .75rem;
}
details.sev-block-box { border-left-style: solid; border-left-color: var(--block); }
details.sev-warn-box { border-left-style: dashed; border-left-color: var(--warn); }
details.sev-note-box { border-left-style: dotted; border-left-color: var(--note); }
details.finding > summary { cursor: pointer; padding: .4rem 0; overflow-wrap: anywhere; }
.where { color: var(--muted); font-size: .9rem; }
.ctx { white-space: pre-wrap; overflow-wrap: anywhere; margin: .5rem 0; }
mark { background: var(--mark); color: var(--mark-fg); padding: 0 .1em; }
.fix::before { content: "Fix: "; font-weight: 600; }
@media print { .chips, .js-only { display: none !important; } }
"""
)

_JS = """\
(function () {
  var root = document.documentElement;
  root.classList.add('js');
  var toggle = document.getElementById('theme');
  if (toggle) toggle.addEventListener('click', function () {
    var dark = root.getAttribute('data-theme') === 'dark' ||
      (!root.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    root.setAttribute('data-theme', dark ? 'light' : 'dark');
  });
  var chips = document.querySelectorAll('button[data-sev]');
  function apply() {
    var on = {};
    chips.forEach(function (c) {
      on[c.getAttribute('data-sev')] = c.getAttribute('aria-pressed') === 'true';
    });
    document.querySelectorAll('details.finding').forEach(function (d) {
      d.hidden = !on[d.getAttribute('data-sev')];
    });
    document.querySelectorAll('section.group').forEach(function (g) {
      g.hidden = g.querySelectorAll('details.finding:not([hidden])').length === 0;
    });
  }
  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
      apply();
    });
  });
  window.addEventListener('beforeprint', function () {
    document.querySelectorAll('details').forEach(function (d) { d.open = true; });
  });
})();
"""


def _sha(text: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()


def e(text: str) -> str:
    return escape(text, quote=True)


def _bar(dim: DimensionResult) -> str:
    if dim.status is not DimensionStatus.ASSESSED or dim.clean_rate is None:
        return ""
    filled = round(dim.clean_rate * 10)
    return f'<span class="bar" aria-hidden="true">{"▓" * filled}{"░" * (10 - filled)}</span> '


def _finding(report: CritiqueReport, f: ReportFinding, index: int) -> str:
    doc = next(d.file_name for d in report.documents if d.source_id == f.source_id)
    before = ("…" if f.context_clipped_before else "") + f.context_before
    after = f.context_after + ("…" if f.context_clipped_after else "")
    sev = f.severity
    detail = f'<p class="detail">{e(f.detail)}</p>' if f.detail else ""
    return (
        f'<details class="finding sev-{sev.value}-box" id="f-{index}" data-sev="{sev.value}">'
        f'<summary><span class="sev sev-{sev.value}">'
        f"{SEVERITY_GLYPH[sev]} {SEVERITY_WORD[sev]}</span> "
        f"“{e(f.quote)}” "
        f'<span class="where">{e(doc)}, {e(f.locator_label)}</span></summary>'
        f'<p class="ctx">{e(before)}<mark>{e(f.quote)}</mark>{e(after)}</p>'
        f"{detail}"
        f'<p class="fix">{e(f.remedy)}</p>'
        "</details>"
    )


def render_html(report: CritiqueReport) -> str:
    style_hash = _sha(_CSS)
    script_hash = _sha(_JS)
    csp = (
        "default-src 'none'; "
        f"style-src '{style_hash}'; script-src '{script_hash}'; "
        "base-uri 'none'; form-action 'none'"
    )
    body: list[str] = []
    body.append(
        f"<header><h1>Probative critique: {e(report.subject)}</h1>"
        f'<p class="muted">{e(run_line(report))}</p>'
        + (f"<p>{e(skipped_line(report) or '')}</p>" if report.skipped else "")
        + f"<p><strong>{e(totals_line(report))}</strong> "
        '<button id="theme" class="js-only" type="button">Toggle theme</button></p></header>'
    )

    rows = []
    for dim in report.dimensions:
        rows.append(
            f'<tr><th scope="row">{e(dim.label)}</th><td class="n">{dim.checked}</td>'
            f"<td>{_bar(dim)}{e(clean_cell(dim))}</td>"
            f'<td class="n">{dim.counts.block}</td><td class="n">{dim.counts.warn}</td>'
            f'<td class="n">{dim.counts.note}</td><td class="n">{e(floor_cell(dim))}</td>'
            f"<td>{e(status_text(dim))}</td></tr>"
        )
    body.append(
        '<h2 id="summary">Summary</h2><div class="scroll"><table>'
        '<caption class="muted">One row per critic. Clean is the share of candidates checked '
        "that drew no blocking or warning finding; the floor is the severity veto.</caption>"
        '<thead><tr><th>Dimension</th><th class="n">Checked</th><th>Clean</th>'
        '<th class="n">Block</th><th class="n">Warn</th><th class="n">Note</th>'
        '<th class="n">Floor (0 to 10)</th><th>Status</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )

    groups = finding_groups(report)
    body.append('<h2 id="findings">Findings</h2>')
    if not groups:
        body.append("<p>No findings.</p>")
    else:
        chips = "".join(
            f'<button type="button" data-sev="{s.value}" aria-pressed="true">'
            f"{SEVERITY_GLYPH[s]} {SEVERITY_LABEL[s]}</button>"
            for s in SEVERITY_ORDER
        )
        body.append(
            f'<div class="chips js-only" role="group" aria-label="Filter by severity">{chips}</div>'
        )
    index = 0
    for severity in SEVERITY_ORDER:
        mine = [g for g in groups if g.severity is severity]
        if not mine:
            continue
        body.append(f"<h3>{e(SEVERITY_LABEL[severity])}</h3>")
        for group in mine:
            items = []
            for f in group.findings:
                items.append(_finding(report, f, index))
                index += 1
            body.append(
                f'<section class="group" data-sev="{severity.value}">'
                f"<h4>{e(group.dimension.label)}: {e(group.headline)} "
                f'<span class="muted">{group_total(group)}</span></h4>'
                f"{''.join(items)}</section>"
            )

    unassessed = [d for d in report.dimensions if d.status is not DimensionStatus.ASSESSED]
    body.append('<h2 id="not-assessed">Not assessed</h2>')
    if unassessed:
        body.append(
            "<ul>"
            + "".join(f"<li>{e(d.label)}: {e(status_text(d))}</li>" for d in unassessed)
            + "</ul>"
        )
    else:
        body.append("<p>Every dimension was assessed.</p>")

    kinds = sorted({k for d in report.documents for k in d.candidates})
    head = "".join(f'<th class="n">{e(k)}</th>' for k in kinds)
    doc_rows = "".join(
        f'<tr><th scope="row">{e(d.file_name)}</th>'
        f"<td>{e(d.format.value)} ({e(d.format_choice)})</td>"
        + "".join(f'<td class="n">{d.candidates.get(k, 0)}</td>' for k in kinds)
        + "</tr>"
        for d in report.documents
    )
    body.append(
        '<h2 id="coverage">Coverage</h2><div class="scroll"><table>'
        f"<thead><tr><th>Document</th><th>Format</th>{head}</tr></thead>"
        f"<tbody>{doc_rows}</tbody></table></div>"
    )
    for d in report.documents:
        if d.rejected:
            detail = ", ".join(f"{k} {v}" for k, v in d.rejected.items())
            body.append(
                f'<p class="muted">Quotes the model proposed that were not found in '
                f"{e(d.file_name)}: {e(detail)}</p>"
            )
    if report.skipped:
        body.append("<h3>Skipped</h3><ul>")
        body.extend(f"<li>{e(s.path)}: {e(s.reason)}</li>" for s in report.skipped)
        body.append("</ul>")
    r = report.run
    body.append(
        f'<p class="muted">{r.input_tokens} input tokens · {r.output_tokens} output tokens · '
        f"{r.jobs} concurrent calls · {e(reply_label(report))} · "
        f"probative {e(report.tool_version)}</p>"
    )

    title = f"Probative critique: {report.subject}"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{e(csp)}">\n'
        f"<title>{e(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n<main>\n"
        + "\n".join(body)
        + f"\n</main>\n<script>{_JS}</script>\n</body>\n</html>\n"
    )
