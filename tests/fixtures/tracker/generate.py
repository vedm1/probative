"""Regenerates the synthetic PB2 tracker fixture corpus. Not run by pytest —
a developer action, per S3 ("Fixtures are committed. Recording is a
developer action, replay is the default.").

Every fixture is hand-shaped to mirror structure confirmed against real
Jira/ADO exports during the PB2 build session (column names, repeated
columns, HTML nesting, XML tag layout) — the real exports themselves are
never committed (CLAUDE.md § Secrets: sample corpora must be synthetic).

    uv run python tests/fixtures/tracker/generate.py
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).parent

DESCRIPTION_WIKI = (
    "The login button does nothing when clicked.\n\n"
    "# Click the login button\n"
    "# Observe that nothing happens\n\n"
    "See *important* note from [~accountid:abc123] and the "
    "[tracking issue|https://example.com/DEMO-0] and !screenshot.png!"
)


def write_jira_visible_csv() -> None:
    """Mirrors the real 'visible fields' export: no Description, Parent key
    or Acceptance Criteria columns at all."""
    rows = [
        [
            "Issue Type",
            "Issue key",
            "Issue id",
            "Summary",
            "Assignee",
            "Status",
            "Priority",
            "Created",
            "Updated",
        ],
        [
            "Bug",
            "DEMO-1",
            "10001",
            "Login button is unresponsive",
            "Alex Kim",
            "Open",
            "High",
            "01/Jan/26 9:00 AM",
            "02/Jan/26 10:00 AM",
        ],
        [
            "Story",
            "DEMO-2",
            "10002",
            "Add password reset flow",
            "Alex Kim",
            "In Progress",
            "Medium",
            "03/Jan/26 9:00 AM",
            "04/Jan/26 10:00 AM",
        ],
        [
            "Epic",
            "DEMO-3",
            "10003",
            "Improve authentication reliability",
            "Jamie Lee",
            "To Do",
            "Medium",
            "05/Jan/26 9:00 AM",
            "05/Jan/26 9:00 AM",
        ],
        [
            "Sub-task",
            "DEMO-4",
            "10004",
            "Write unit tests for reset flow",
            "Alex Kim",
            "Done",
            "Low",
            "06/Jan/26 9:00 AM",
            "07/Jan/26 9:00 AM",
        ],
    ]
    with (HERE / "jira_visible.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def write_jira_all_fields_csv() -> None:
    """Mirrors the real 'all fields' export's shape: canonical columns
    interspersed with repeated-name columns (Labels, Watchers, Comment)
    that PB2 does not extract, plus a real Acceptance Criteria custom
    field the real sample never had."""
    header = [
        "Summary",
        "Issue key",
        "Issue Type",
        "Status",
        "Labels",
        "Labels",
        "Parent",
        "Parent key",
        "Parent summary",
        "Description",
        "Watchers",
        "Watchers",
        "Custom field (Acceptance Criteria)",
        "Comment",
        "Comment",
    ]
    rows = [
        header,
        [
            "Login button is unresponsive",
            "DEMO-1",
            "Bug",
            "Open",
            "bug-triage",
            "",
            "",
            "",
            "",
            DESCRIPTION_WIKI,
            "Alex Kim",
            "",
            "",
            "09/Jun/26;user1;first comment",
            "",
        ],
        [
            "Add password reset flow",
            "DEMO-2",
            "Story",
            "In Progress",
            "",
            "",
            "10001",
            "DEMO-1",
            "Login button is unresponsive",
            "Reset flow lets users regain access.",
            "Alex Kim",
            "Jamie Lee",
            "Given a user requests reset, when they submit their email, "
            "then a reset link is emailed within 5 minutes.",
            "",
            "",
        ],
        [
            "Improve authentication reliability",
            "DEMO-3",
            "Epic",
            "To Do",
            "",
            "",
            "",
            "",
            "",
            "",
            "Jamie Lee",
            "",
            "",
            "",
            "",
        ],
        [
            "Write unit tests for reset flow",
            "DEMO-4",
            "Sub-task",
            "Done",
            "testing",
            "backend",
            "10002",
            "DEMO-2",
            "Add password reset flow",
            "Cover expiry and invalid token cases.",
            "Alex Kim",
            "",
            "",
            "",
            "",
        ],
    ]
    with (HERE / "jira_all_fields.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def write_jira_malformed_csv() -> None:
    """Missing 'Status' — one of jira_csv's required columns."""
    rows = [
        ["Issue key", "Issue Type", "Summary"],
        ["DEMO-1", "Bug", "Login button is unresponsive"],
    ]
    with (HERE / "jira_malformed_missing_status.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


_ISSUE_ROW = """
<tr class="issuerow" data-rowkey="{key}">
<td class="issuetype">{type_}</td>
<td class="issuekey"><a class="issue-link" data-issue-key="{key}" \
href="https://example.atlassian.net/browse/{key}">{key}</a></td>
<td class="summary">{summary}</td>
<td class="status"><span class="jira-issue-status-lozenge">{status}</span></td>
<td class="parent">{parent}</td>
<td class="description">{description}</td>
<td class="customfield_19999">{acceptance_criteria}</td>
</tr>"""

_HTML_TEMPLATE = """<html xmlns="http://www.w3.org/TR/REC-html40">
<head><title>Jira</title></head>
<body>
<table id="issuetable" class="aui" border="1" cellpadding="3" cellspacing="1" width="100%">
<thead>
<tr class="rowHeader">
<th class="colHeaderLink headerrow-issuetype" data-id="issuetype">Issue Type</th>
<th class="colHeaderLink headerrow-issuekey" data-id="issuekey">Key</th>
<th class="colHeaderLink headerrow-summary" data-id="summary">Summary</th>
<th class="colHeaderLink headerrow-status" data-id="status">Status</th>
<th class="colHeaderLink headerrow-parent" data-id="parent">Parent</th>
<th class="colHeaderLink headerrow-description" data-id="description">Description</th>
<th class="colHeaderLink headerrow-customfield_19999" \
data-id="customfield_19999">Acceptance Criteria</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""


def write_jira_issues_html() -> None:
    description_html = DESCRIPTION_WIKI.replace("\n", "<br/>")
    rows = [
        _ISSUE_ROW.format(
            key="DEMO-1",
            type_="Bug",
            summary="Login button is unresponsive",
            status="Open",
            parent="",
            description=description_html,
            acceptance_criteria="",
        ),
        _ISSUE_ROW.format(
            key="DEMO-2",
            type_="Story",
            summary="Add password reset flow",
            status="In Progress",
            parent="DEMO-1",
            description="Reset flow lets users regain access.",
            acceptance_criteria=(
                "Given a user requests reset, when they submit their email, "
                "then a reset link is emailed within 5 minutes."
            ),
        ),
        _ISSUE_ROW.format(
            key="DEMO-3",
            type_="Epic",
            summary="Improve authentication reliability",
            status="To Do",
            parent="",
            description="",
            acceptance_criteria="",
        ),
        _ISSUE_ROW.format(
            key="DEMO-4",
            type_="Sub-task",
            summary="Write unit tests for reset flow",
            status="Done",
            parent="DEMO-2",
            description="Cover expiry and invalid token cases.",
            acceptance_criteria="",
        ),
    ]
    (HERE / "jira_issues.html").write_text(
        _HTML_TEMPLATE.format(rows="\n".join(rows)), encoding="utf-8"
    )


def write_jira_malformed_html() -> None:
    """Missing the 'status' column entirely."""
    html = """<html><body>
<table id="issuetable">
<thead><tr class="rowHeader">
<th class="colHeaderLink headerrow-issuetype" data-id="issuetype">Issue Type</th>
<th class="colHeaderLink headerrow-issuekey" data-id="issuekey">Key</th>
<th class="colHeaderLink headerrow-summary" data-id="summary">Summary</th>
</tr></thead>
<tbody>
<tr class="issuerow">
<td class="issuetype">Bug</td>
<td class="issuekey">DEMO-1</td>
<td class="summary">Login button is unresponsive</td>
</tr>
</tbody>
</table>
</body></html>
"""
    (HERE / "jira_malformed_missing_status.html").write_text(html, encoding="utf-8")


_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="0.92">
<channel>
<title>Jira</title>
{items}
</channel>
</rss>
"""

_ITEM_TEMPLATE = """<item>
<title>[{key}] {summary}</title>
<key id="{numeric_id}">{key}</key>
<summary>{summary}</summary>
<type id="1">{type_}</type>
<status id="1">{status}</status>
{parent}
<description>{description}</description>
{customfields}
</item>"""


def write_jira_export_xml() -> None:
    description_html_1 = (
        "&lt;p&gt;The login button does nothing when clicked.&lt;/p&gt;"
        "&lt;p&gt;STEPS TO REPRODUCE&lt;/p&gt;"
        "&lt;ol&gt;&lt;li&gt;Click the login button&lt;/li&gt;"
        "&lt;li&gt;Observe that nothing happens&lt;/li&gt;&lt;/ol&gt;"
    )
    items = [
        _ITEM_TEMPLATE.format(
            key="DEMO-1",
            numeric_id="20001",
            summary="Login button is unresponsive",
            type_="Bug",
            status="Open",
            parent="",
            description=description_html_1,
            customfields="",
        ),
        _ITEM_TEMPLATE.format(
            key="DEMO-2",
            numeric_id="20002",
            summary="Add password reset flow",
            type_="Story",
            status="In Progress",
            parent='<parent id="20001">DEMO-1</parent>',
            description="&lt;p&gt;Reset flow lets users regain access.&lt;/p&gt;",
            customfields=(
                "<customfields><customfield><customfieldname>Acceptance Criteria"
                "</customfieldname><customfieldvalues><customfieldvalue>"
                "Given a user requests reset, when they submit their email, "
                "then a reset link is emailed within 5 minutes."
                "</customfieldvalue></customfieldvalues></customfield></customfields>"
            ),
        ),
        _ITEM_TEMPLATE.format(
            key="DEMO-3",
            numeric_id="20003",
            summary="Improve authentication reliability",
            type_="Epic",
            status="To Do",
            parent="",
            description="",
            customfields="",
        ),
        _ITEM_TEMPLATE.format(
            key="DEMO-4",
            numeric_id="20004",
            summary="Write unit tests for reset flow",
            type_="Sub-task",
            status="Done",
            parent='<parent id="20002">DEMO-2</parent>',
            description="&lt;p&gt;Cover expiry and invalid token cases.&lt;/p&gt;",
            customfields="",
        ),
    ]
    (HERE / "jira_export.xml").write_text(
        _XML_TEMPLATE.format(items="\n".join(items)), encoding="utf-8"
    )


def write_jira_no_table_html() -> None:
    """A page with no <table id="issuetable"> at all — not an issue-navigator
    export."""
    (HERE / "jira_no_table.html").write_text(
        "<html><body><p>Not an issue export.</p></body></html>\n", encoding="utf-8"
    )


def write_jira_not_well_formed_xml() -> None:
    """Unclosed tag — not parseable XML at all."""
    (HERE / "jira_not_well_formed.xml").write_text(
        '<?xml version="1.0"?><rss><channel><item><key>DEMO-1</key>\n', encoding="utf-8"
    )


def write_jira_malformed_xml() -> None:
    """One item missing <status> entirely."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="0.92"><channel><title>Jira</title>
<item>
<title>[DEMO-1] Login button is unresponsive</title>
<key id="20001">DEMO-1</key>
<summary>Login button is unresponsive</summary>
<type id="1">Bug</type>
<description>broken</description>
</item>
</channel></rss>
"""
    (HERE / "jira_malformed_missing_status.xml").write_text(xml, encoding="utf-8")


def write_ado_issues_csv() -> None:
    rows = [
        ["Area Path", "Parent", "ID", "Work Item Type", "Title", "Description", "State", "Tags"],
        [
            "Product\\Auth",
            "",
            "30001",
            "Bug",
            "Login button is unresponsive",
            "<div>The button does nothing when clicked.</div>",
            "Active",
            "P1",
        ],
        [
            "Product\\Auth",
            "99999",
            "30002",
            "Product Backlog Item",
            "Add password reset flow",
            "<div>As a user</div><div>I need to reset my password&nbsp;</div>",
            "New",
            "",
        ],
        [
            "Product\\Auth",
            "30002",
            "30003",
            "Task",
            "Write unit tests for reset flow",
            "<div>Cover expiry and invalid token cases.</div>",
            "Closed",
            "",
        ],
    ]
    with (HERE / "ado_issues.csv").open("w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def write_ado_with_acceptance_criteria_csv() -> None:
    rows = [
        [
            "ID",
            "Work Item Type",
            "Title",
            "Description",
            "State",
            "Parent",
            "Acceptance Criteria",
        ],
        [
            "30002",
            "Product Backlog Item",
            "Add password reset flow",
            "<div>As a user I need to reset my password</div>",
            "New",
            "",
            "<div>Given a request, a reset email is sent within 5 minutes.</div>",
        ],
    ]
    with (HERE / "ado_with_acceptance_criteria.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def write_ado_malformed_csv() -> None:
    """Missing 'State' — one of ado_csv's required columns."""
    rows = [
        ["ID", "Work Item Type", "Title"],
        ["30001", "Bug", "Login button is unresponsive"],
    ]
    with (HERE / "ado_malformed_missing_state.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


if __name__ == "__main__":
    write_jira_visible_csv()
    write_jira_all_fields_csv()
    write_jira_malformed_csv()
    write_jira_issues_html()
    write_jira_malformed_html()
    write_jira_no_table_html()
    write_jira_export_xml()
    write_jira_malformed_xml()
    write_jira_not_well_formed_xml()
    write_ado_issues_csv()
    write_ado_with_acceptance_criteria_csv()
    write_ado_malformed_csv()
    print("Wrote PB2 tracker fixtures to", HERE)
