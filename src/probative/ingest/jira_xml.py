"""Jira RSS/XML issue export (`Export XML` on a filter/search).

`<description>` is genuine escaped HTML (confirmed: `<p>`, `<ol><li>` in a
real export) — a different normalisation path from jira_csv/jira_html's
wiki markup — via `probative.ingest._html`. Acceptance Criteria, when
present, lives under `<customfields>` and is matched by
`<customfieldname>` text (`"Acceptance Criteria"`, case-insensitive) since
custom field ids are Jira-instance-specific.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from probative.core.evidence import CorruptSourceError, UnrecognisedTrackerFormatError
from probative.ingest import _html
from probative.ingest._extracted import ExtractedDocument
from probative.ingest._tracker_text import TrackerTextBuilder

NORMALIZATION_VERSION = "jira_xml/1"


def _text(item: ET.Element, tag: str) -> str | None:
    el = item.find(tag)
    if el is None or el.text is None:
        return None
    return el.text


def _acceptance_criteria(item: ET.Element) -> str | None:
    for customfield in item.findall("./customfields/customfield"):
        name_el = customfield.find("customfieldname")
        if name_el is None or name_el.text is None:
            continue
        if name_el.text.strip().lower() != "acceptance criteria":
            continue
        values = customfield.findall("./customfieldvalues/customfieldvalue")
        text = "\n".join(v.text for v in values if v.text)
        return text or None
    return None


def extract(path: Path) -> ExtractedDocument:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise CorruptSourceError(path, f"not well-formed XML: {exc}") from exc

    items = root.findall("./channel/item")
    builder = TrackerTextBuilder()
    for item in items:
        key = _text(item, "key")
        type_ = _text(item, "type")
        status = _text(item, "status")
        summary = _text(item, "summary")
        if key is None or type_ is None or status is None or summary is None:
            title = _text(item, "title") or "<untitled item>"
            missing = [
                name
                for name, value in [
                    ("key", key),
                    ("type", type_),
                    ("status", status),
                    ("summary", summary),
                ]
                if value is None
            ]
            raise UnrecognisedTrackerFormatError(
                path,
                f"item {title!r} is missing required element(s) for jira_xml: {', '.join(missing)}",
            )

        parent_el = item.find("parent")
        parent_key = parent_el.text if parent_el is not None else None

        description_raw = _text(item, "description")
        description = _html.to_text(description_raw) if description_raw else None
        acceptance_criteria_raw = _acceptance_criteria(item)
        acceptance_criteria = (
            _html.to_text(acceptance_criteria_raw) if acceptance_criteria_raw else None
        )

        builder.add_issue(
            key=key,
            type_=type_,
            status=status,
            parent_key=parent_key,
            summary=summary,
            description=description,
            acceptance_criteria=acceptance_criteria,
        )

    return builder.build(NORMALIZATION_VERSION)
