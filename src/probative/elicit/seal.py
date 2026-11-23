"""Seal a session (PB14): render the transcript, ingest it as T3, build the nodes.

One transcript file per evidence kind, written to `<source_root>/.elicitation/`. The
leading dot keeps `EvidenceLedger` from rediscovering it (probed 2026-11-16: its
discovery skips dot paths), and `Source.path` accepts it. Every claim of a file shares
that one `Source`, so its independent-source count is 1 (OI39, OI46). A sealed file is
never changed: sealing the same turns again writes the same bytes, and a file that
differs is refused.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from probative.core.evidence import EvidenceKind, Tier
from probative.core.graph.edges import Edge
from probative.core.graph.nodes import NodeBase
from probative.elicit.build import Outcome, build, outcome, render, words
from probative.elicit.types import Turn
from probative.ingest import ingest
from probative.ledger.build import source_node

SEAL_DIR: Final = ".elicitation"


class SealError(Exception):
    pass


@dataclass(frozen=True)
class Sealed:
    nodes: tuple[NodeBase, ...]
    edges: tuple[Edge, ...]
    claims_by_turn: dict[int, str]
    files: tuple[Path, ...]


def seal(
    session: str,
    turns: Sequence[Turn],
    *,
    propositions: Mapping[int, str | None],
    abouts: Mapping[int, str | None],
    source_root: Path,
    owner: str,
    now: datetime,
    tainted: frozenset[int] = frozenset(),
) -> Sealed:
    """`propositions[i]` is the source claim's text a `confirm` or `deny` turn answered;
    `abouts[i]` is that claim's id (for a `deny`). Both keyed by turn index."""
    by_kind: dict[EvidenceKind, list[Turn]] = {}
    for turn in turns:
        if turn.evidence_kind is None:
            raise SealError(f"turn {turn.index} has no evidence kind")
        by_kind.setdefault(turn.evidence_kind, []).append(turn)
    nodes: dict[str, NodeBase] = {}
    edges: dict[str, Edge] = {}
    claims: dict[int, str] = {}
    files: list[Path] = []
    for kind in sorted(by_kind, key=lambda k: k.value):
        group = by_kind[kind]
        pairs = [(t, words(t, propositions.get(t.index)), abouts.get(t.index)) for t in group]
        makes_claim = any(t.index not in tainted and outcome(t) is Outcome.CLAIM for t in group)
        if not makes_claim:
            # no claim to anchor: only Questions, which need no transcript
            only = build(pairs, None, None, owner=owner, now=now, tainted=tainted)
            nodes.update({n.id: n for n in only.nodes})
            edges.update({e.id: e for e in only.edges})
            continue
        text = render(f"{session}-{kind.value}", [(t, w) for t, w, _ in pairs])
        path = source_root / SEAL_DIR / f"{session}-{kind.value}.md"
        _write_once(path, text)
        files.append(path)
        core = ingest(path, tier=Tier.T3, kind=kind)
        source = source_node(core, source_root, owner=owner, now=now)
        built_all = build(pairs, core, source, owner=owner, now=now, tainted=tainted)
        nodes[source.id] = source
        nodes.update({n.id: n for n in built_all.nodes})
        edges.update({e.id: e for e in built_all.edges})
        claims.update(built_all.claims_by_turn)
    return Sealed(
        tuple(nodes[i] for i in sorted(nodes)),
        tuple(edges[i] for i in sorted(edges)),
        claims,
        tuple(files),
    )


def _write_once(path: Path, text: str) -> None:
    data = text.encode("utf-8")
    if path.is_file():
        if path.read_bytes() != data:
            raise SealError(
                f"{path.name} exists with different content; a sealed file never changes"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
