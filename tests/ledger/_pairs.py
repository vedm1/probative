"""The synthetic judge fixtures (PB13): invented statements, one author (OI21)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from probative.ledger.contradict import RUBRIC_PATH

FIXTURES = RUBRIC_PATH.parent / "fixtures"


@dataclass(frozen=True)
class Pair:
    id: str
    a: str
    b: str
    accept: frozenset[str]
    group: str


def _load(sub: str) -> dict[str, object]:
    raw: dict[str, object] = json.loads((FIXTURES / sub / "pairs.json").read_text(encoding="utf-8"))
    return raw


def _rows(doc: dict[str, object], key: str, expected: str) -> list[Pair]:
    rows = doc.get(key, [])
    assert isinstance(rows, list)
    return [Pair(r["id"], r["a"], r["b"], frozenset({expected}), key) for r in rows]


def contradicting(split: str) -> list[Pair]:
    return _rows(_load("contradicting"), split, "contradicts")


def consistent(split: str, *, hard: bool = False) -> list[Pair]:
    return _rows(_load("consistent"), f"hard_{split}" if hard else split, "consistent")


def stress() -> list[Pair]:
    doc = _load("stress")
    rows = doc["stress"]
    assert isinstance(rows, list)
    return [Pair(r["id"], r["a"], r["b"], frozenset(r["accept"]), "stress") for r in rows]


def split(name: str) -> list[Pair]:
    """Every pair in one split: `dev`, `held_out` or `stress`."""
    if name == "stress":
        return stress()
    return [
        *contradicting(name),
        *consistent(name),
        *consistent(name, hard=True),
    ]
