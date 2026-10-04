from __future__ import annotations

from tests.extract._helpers import FIXTURES

GOLD = FIXTURES / "gold"

# (document, gold labels) pairs.
CORPUS = [
    ("prd_payments.md", "prd_payments_md.json"),
    ("prd_payments.pdf", "prd_payments_pdf.json"),
    ("memo_logistics.txt", "memo_logistics.json"),
]
