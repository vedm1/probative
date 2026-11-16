"""How many independent sources stand behind a claim (PB13, D4; OI39).

The rule lives with the formula that reads it (`probative.formulas.confidence`),
because the validator recomputes it on every commit. This module re-exports it
for callers that think of it as ledger vocabulary.
"""

from probative.formulas.confidence import independent_sources as independent_sources

__all__ = ["independent_sources"]
