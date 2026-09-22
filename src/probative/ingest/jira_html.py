"""Jira issue-navigator HTML export ("Export current fields to HTML" — an
Excel-flavoured `<table id="issuetable">`, not a Confluence page).

Uses BeautifulSoup (stdlib `html.parser` backend, no extra parser
dependency) because real cells nest markup a regex cannot safely pick
apart — a status cell is a lozenge `<span>`, a key cell is an
`<a data-issue-key="...">` (confirmed against a real export).

Built-in fields share one field-id vocabulary between `<th data-id="...">`
and its column's `<td class="...">` (`issuekey`, `issuetype`, `status`,
`summary`, `description`, `parent`). Acceptance Criteria, like any custom
field, gets an instance-specific `customfield_NNNNN` id, so it is matched
by the `<th>`'s visible label text instead.

Description cells carry Jira wiki markup with `<br/>` standing in for
newlines (confirmed against a real export) — not real HTML — so `<br/>` is
turned back into `\\n` before the shared `probative.ingest._wiki`
normaliser runs, the same path jira_csv uses.
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, Tag

from probative.core.evidence import CorruptSourceError, UnrecognisedTrackerFormatError
from probative.ingest import _wiki
from probative.ingest._extracted import ExtractedDocument
from probative.ingest._tracker_text import TrackerTextBuilder

NORMALIZATION_VERSION = "jira_html/1"

_REQUIRED_FIELD_IDS = ["issuekey", "issuetype", "status", "summary"]
_ACCEPTANCE_CRITERIA_LABEL = "acceptance criteria"


def _field_id_of(tag: Tag) -> str | None:
    classes = tag.get("class")
    if not classes:
        return None
    return str(classes[0])


def _cell_text_for_description(td: Tag) -> str:
    html_fragment = "".join(str(c) for c in td.contents)
    with_newlines = html_fragment.replace("<br/>", "\n").replace("<br>", "\n")
    return _wiki.to_text(BeautifulSoup(with_newlines, "html.parser").get_text())


def extract(path: Path) -> ExtractedDocument:
    try:
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    except UnicodeDecodeError as exc:
        raise CorruptSourceError(path, f"not valid UTF-8: {exc}") from exc

    table = soup.find("table", id="issuetable")
    if not isinstance(table, Tag):
        raise UnrecognisedTrackerFormatError(path, 'no <table id="issuetable"> found')

    label_by_field_id: dict[str, str] = {}
    for th in table.select("thead th[data-id]"):
        label_by_field_id[str(th["data-id"])] = th.get_text(strip=True)

    missing = [f for f in _REQUIRED_FIELD_IDS if f not in label_by_field_id]
    if missing:
        raise UnrecognisedTrackerFormatError(
            path, f"missing required column(s) for jira_html: {', '.join(missing)}"
        )

    acceptance_field_id = next(
        (
            field_id
            for field_id, label in label_by_field_id.items()
            if label.strip().lower() == _ACCEPTANCE_CRITERIA_LABEL
        ),
        None,
    )

    builder = TrackerTextBuilder()
    for row in table.select("tbody tr.issuerow"):
        cells: dict[str, Tag] = {}
        for td in row.find_all("td", recursive=False):
            if not isinstance(td, Tag):
                continue
            field_id = _field_id_of(td)
            if field_id is not None:
                cells[field_id] = td

        key = cells["issuekey"].get_text(strip=True)
        type_ = cells["issuetype"].get_text(strip=True)
        status = cells["status"].get_text(strip=True)
        summary = cells["summary"].get_text(strip=True)
        parent_td = cells.get("parent")
        parent_key = parent_td.get_text(strip=True) if parent_td is not None else ""

        description_td = cells.get("description")
        description = (
            _cell_text_for_description(description_td) if description_td is not None else None
        )

        acceptance_criteria = None
        if acceptance_field_id is not None and acceptance_field_id in cells:
            acceptance_criteria = _cell_text_for_description(cells[acceptance_field_id])

        builder.add_issue(
            key=key,
            type_=type_,
            status=status,
            parent_key=parent_key or None,
            summary=summary,
            description=description or None,
            acceptance_criteria=acceptance_criteria or None,
        )

    return builder.build(NORMALIZATION_VERSION)
