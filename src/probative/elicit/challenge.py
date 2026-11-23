"""Challenge in the moment (PB14): a new claim of the respondent's against current claims.

It reuses PB13's pre-filter, judge, rubric and `Question` template, so a contradiction is
stated and preserved, never averaged, and no one is named (I9). The difference is the scope:
one new claim against the claims already in the graph is O(n), where the ledger's sweep is
O(n^2). The pre-filter is lexical, so a contradiction worded with no shared word is missed
(OI44); a miss is expected and not hidden.

Judged pairs are cached in the session directory, keyed by the two claim ids and the model,
so resuming a session repeats no model call and replays to the same graph.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from probative.core.evidence import Tier
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, NodeBase, Question
from probative.ledger.contradict import (
    MIN_JACCARD,
    MIN_SHARED_WORDS,
    QUESTION_TEMPLATE,
    PairVerdict,
    content_tokens,
    where,
)

Judge = Callable[[Claim, Claim], PairVerdict]


class VerdictCache:
    """`verdicts.jsonl`: one line per judged pair. A cache of facts about two fixed
    statements, not graph state, so a rejected patch does not invalidate it."""

    def __init__(self, path: Path, model: str) -> None:
        self._path = path
        self._model = model
        self._seen: dict[tuple[str, str], PairVerdict] = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                d = json.loads(line)
                if d["model"] == model:
                    self._seen[(d["a"], d["b"])] = PairVerdict(d["verdict"])

    def get(self, a: str, b: str) -> PairVerdict | None:
        return self._seen.get((a, b))

    def put(self, a: str, b: str, verdict: PairVerdict) -> None:
        self._seen[(a, b)] = verdict
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps({"a": a, "b": b, "model": self._model, "verdict": verdict.value}) + "\n"
            )


def candidates_for(graph: Graph, claim: Claim) -> list[Claim]:
    """Current claims worth comparing with `claim`: not T5, not itself, sharing enough words,
    not already joined by a `CONTRADICTS` edge."""
    mine = content_tokens(claim.text)
    found: list[Claim] = []
    for other in sorted(graph.current(), key=lambda n: n.id):
        if not isinstance(other, Claim) or other.id == claim.id or other.tier is Tier.T5:
            continue
        theirs = content_tokens(other.text)
        shared, union = len(mine & theirs), len(mine | theirs)
        jaccard = shared / union if union else 0.0
        if shared < MIN_SHARED_WORDS and jaccard < MIN_JACCARD:
            continue
        if any(e.dst == other.id for e in graph.out_edges(claim.id, EdgeType.CONTRADICTS)) or any(
            e.dst == claim.id for e in graph.out_edges(other.id, EdgeType.CONTRADICTS)
        ):
            continue
        found.append(other)
    return found


def challenge(
    graph: Graph,
    new_claims: Sequence[Claim],
    judge: Judge,
    cache: VerdictCache,
    *,
    owner: str,
    now: datetime,
) -> tuple[list[NodeBase], list[Edge], int]:
    """Nodes and edges for every contradiction between a new claim and a current one, and the
    number of pairs judged (cache hits are not judged)."""
    nodes: dict[str, NodeBase] = {}
    edges: dict[str, Edge] = {}
    judged = 0
    for new in sorted(new_claims, key=lambda c: c.id):
        for other in candidates_for(graph, new):
            verdict = cache.get(new.id, other.id)
            if verdict is None:
                verdict = judge(new, other)
                cache.put(new.id, other.id, verdict)
                judged += 1
            if verdict is not PairVerdict.CONTRADICTS:
                continue
            q = Question.make(
                text=QUESTION_TEMPLATE.format(
                    a=new.text, a_where=where(graph, new), b=other.text, b_where=where(graph, other)
                ),
                raised_by="contradiction",
                owner=owner,
                asserted_at=now,
            )
            nodes.setdefault(q.id, q)
            for kind, src, dst in (
                (EdgeType.CONTRADICTS, new.id, other.id),
                (EdgeType.RAISED_ABOUT, q.id, new.id),
                (EdgeType.RAISED_ABOUT, q.id, other.id),
            ):
                e = Edge.make(type=kind, src=src, dst=dst, owner=owner, asserted_at=now)
                edges.setdefault(e.id, e)
    return [nodes[i] for i in sorted(nodes)], [edges[i] for i in sorted(edges)], judged
