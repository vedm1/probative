"""Rank helpers for comparing two scorings of the same items.

Both opportunity formulas are always computed and both are shown; when they
disagree on the top of the list, that is a signal the ratings are not
discriminating (DESIGN §8). PB18 raises the `Question` node. This module only
answers which ids the two top-n sets do not share. It returns ids, never a
number, and holds no judgement.
"""

from __future__ import annotations

from collections.abc import Mapping


def top_n(scores: Mapping[str, float], n: int) -> tuple[str, ...]:
    """The `n` highest-scoring ids, ties broken by id so the order is stable."""
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    return tuple(sorted(scores, key=lambda k: (-scores[k], k))[:n])


def top_n_disagree(a: Mapping[str, float], b: Mapping[str, float], n: int = 5) -> tuple[str, ...]:
    """Ids that are in exactly one of the two top-`n` sets, sorted."""
    return tuple(sorted(set(top_n(a, n)) ^ set(top_n(b, n))))
