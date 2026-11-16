"""A small synthetic corpus for the ledger (PB13). Invented text only: the real
dogfood corpus (OI4) is still open, so every number measured on this is a number
about synthetic data."""

from __future__ import annotations

from pathlib import Path

from probative.extract.prompts import ConstraintOutput, GeneralOutput, RawQuote
from tests.ledger._helpers import write

APPROVALS_SLOW = "Approvals take three days or more."
APPROVALS_FAST = "Approvals take under one day."
REIMBURSE = "Expenses are reimbursed monthly."
MEDIAN = "Median approval time was 74 hours in October."
SECOND = "Every request over the limit needs a second approver."

FILES = {
    "interviews/a.md": f"# Interview A\n\n{APPROVALS_SLOW}\n{REIMBURSE}\n",
    "interviews/b.md": f"# Interview B\n\n{APPROVALS_SLOW}\n{APPROVALS_FAST}\n",
    "misc/notes.md": "Loose notes with no folder cue.\n",
    "ops/metrics/october.md": f"# October\n\n{MEDIAN}\n",
    "research/market.md": "Analyst view of the market.\n",
    "sop/approvals.md": f"# Approvals SOP\n\n{SECOND}\n",
}
CLAIMS = {
    "interviews/a.md": [APPROVALS_SLOW, REIMBURSE],
    "interviews/b.md": [APPROVALS_SLOW, APPROVALS_FAST],
    "ops/metrics/october.md": [MEDIAN],
    "sop/approvals.md": [SECOND],
}
HELD_OUT = ["misc/notes.md", "research/market.md"]


def build(root: Path) -> None:
    for rel, text in FILES.items():
        write(root, rel, text)


def extraction_script() -> list[GeneralOutput | ConstraintOutput]:
    """What a model returns for each ingested file, in sorted path order: the
    general pass, then the constraint pass."""
    out: list[GeneralOutput | ConstraintOutput] = []
    for rel in sorted(CLAIMS):
        out.append(GeneralOutput(claims=[RawQuote(quote=q) for q in CLAIMS[rel]]))
        out.append(ConstraintOutput())
    return out


def _claims_all() -> list[list[str]]:
    return list(CLAIMS.values())
