"""The text the critique renderers may print that is not from the report (I5).

Every entry is template text: a column header, a severity or status word, or a
sentence with its numbers replaced by `#`. `tests/render/test_i5_projection.py`
renders each renderer with every report string blanked and fails on any run of
text that is not in this set, so a sentence added to a renderer fails until it is
added here, in a diff a reviewer reads. Add nothing here that states a finding,
a judgement or a fact about the document: those belong in the report model, where
they have a source (I1, I5).

Entries are in the normal form of `probative.core.projection.normalise_run`.
"""

from __future__ import annotations

FIXED_LABELS: frozenset[str] = frozenset(
    {
        "# (reference model",
        "# blocking",
        "# characters",
        "# concurrent calls",
        "# document",
        "# file skipped, not assessed (see Coverage",
        "# flagged",
        "# input tokens",
        "# notes",
        "# of #",
        "# of # (#%",
        "# output tokens",
        "# pages",
        "# successful model calls",
        "# undecided, counted clean",
        "# warnings",
        "#: # (# flagged",
        "#: # (# of #",
        "#: INCOMPLETE: # not judged, # extraction pass failed",
        "#: nothing found to check",
        "#s",
        "BLOCKED",
        "Block",
        "Blocking",
        "Checked",
        "Clean",
        "Coverage",
        "Dimension",
        "Document",
        "Filter by severity",
        "Findings",
        "Fix: #",
        "Floor (# to #",
        "Format",
        "INCOMPLETE: # not judged, # extraction pass failed",
        "No findings",
        "Not assessed",
        "Note",
        "Notes",
        (
            "One row per critic. Clean is the share of candidates checked that drew no "
            "blocking or warning finding; the floor is the severity veto"
        ),
        "Probative critique: #",
        "Quotes the model proposed that were not found in #: # #",
        "Quotes the model proposed that were not found: #: # #",
        "Skipped",
        "Status",
        "Summary",
        "Toggle theme",
        "Warn",
        "Warnings",
        "clean",
        "critics reply with flagged items only",
        "detected",
        "forced",
        "nothing found to check",
        "probative #",
        "small sample",
        "warnings",
        "▲ WARN",
        "▲ Warnings",
        "✗ BLOCK",
        "✗ Blocking",
    }
)
