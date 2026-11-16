"""Run the pair judge over a split and score it against the fixtures' labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from probative.core.evidence import Tier
from probative.ledger.build import new_claim
from probative.ledger.contradict import judge_pair
from probative.llm import Provider
from tests.ledger import _pairs
from tests.ledger._helpers import NOW, OWNER

RECORDINGS = Path(__file__).parent.parent / "fixtures" / "ledger" / "recordings"
HINT = (
    "Record with `ANTHROPIC_API_KEY=... PB13_SPLIT=<dev|stress|held_out> uv run pytest -m live "
    "tests/ledger/test_live_record_contradict.py -s`"
)


@dataclass(frozen=True)
class Scored:
    verdicts: dict[str, str]
    caught: int
    missed: list[str]
    false_positives: list[str]
    as_labelled: int
    total: int


def judge_split(provider: Provider, model: str, name: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in _pairs.split(name):
        x = new_claim(pair.a, Tier.T1, None, owner=OWNER, now=NOW)
        y = new_claim(pair.b, Tier.T1, None, owner=OWNER, now=NOW)
        first, second = sorted((x, y), key=lambda c: c.id)  # the production order
        verdict, _ = judge_pair(provider, model, first, second)
        out[pair.id] = verdict.value
    return out


def score(name: str, verdicts: dict[str, str]) -> Scored:
    pairs = _pairs.split(name)
    seeded = [p for p in pairs if p.accept == frozenset({"contradicts"}) and p.group != "stress"]
    clean = [p for p in pairs if p.accept == frozenset({"consistent"}) and p.group != "stress"]
    return Scored(
        verdicts=verdicts,
        caught=sum(verdicts[p.id] == "contradicts" for p in seeded),
        missed=[p.id for p in seeded if verdicts[p.id] != "contradicts"],
        false_positives=[p.id for p in clean if verdicts[p.id] == "contradicts"],
        as_labelled=sum(verdicts[p.id] in p.accept for p in pairs),
        total=len(pairs),
    )
