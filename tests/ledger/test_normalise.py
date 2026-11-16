# ruff: noqa: RUF001  (the cases are deliberately ambiguous characters)
from __future__ import annotations

import pytest

from probative.ledger.normalise import normalise


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Approvals take days.", "Approvals take days."),
        ("  Approvals   take\n days.  ", "Approvals take days."),
        ("- Approvals take days.", "Approvals take days."),
        ("* Approvals take days.", "Approvals take days."),
        ("• Approvals take days.", "Approvals take days."),
        ("3. Approvals take days.", "Approvals take days."),
        ("12) Approvals take days.", "Approvals take days."),
        ("Approvals take days.", "Approvals take days."),  # NFKC + whitespace
        (
            "Ａpprovals take days.",
            "Approvals take days.",
        ),  # full-width letter, NFKC
    ],
)
def test_normalise_cases(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_case_and_punctuation_are_kept() -> None:
    assert normalise("approvals take days") != normalise("Approvals take days.")


def test_only_one_leading_marker_is_removed() -> None:
    assert normalise("- - Approvals") == "- Approvals"


def test_a_number_inside_the_text_is_not_a_marker() -> None:
    assert normalise("3 days is too long.") == "3 days is too long."
    assert normalise("3.5 days is too long.") == "3.5 days is too long."


def test_normalise_is_idempotent() -> None:
    once = normalise("  - Approvals   take days. ")
    assert normalise(once) == once
