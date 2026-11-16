"""`EvidenceLedger`: the P0 producer (PB13, DESIGN §13).

It finds the documents under the run's source root that the graph does not hold
yet, classifies each (D6), extracts candidate claims with PB4's extractor, builds
`Source`, `EvidenceSpan` and `Claim` nodes, and opens a `Question` where two
claims disagree (D8). It returns a proposal. It never writes the graph and never
supplies a number: every `Computed` it proposes has `value=None`, and the
`Committer` fills it from the registered formula (I4).

Scope: it ingests the formats `probative.ingest.ingest` reads. A tracker or
Confluence export needs its own ingest call, so the caller ingests and
classifies those and passes them as `extra_sources`.

Cost is the provider's own `TokenUsage` (extraction plus the pair judge), not a
figure the model reports (OI37c).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from probative.agents.contract import AgentResult, CostRecord, SelfAssessment, TierPolicy
from probative.core.candidates import ExtractionResult
from probative.core.evidence import IngestError, Tier
from probative.core.evidence import Source as CoreSource
from probative.core.graph.edges import Edge
from probative.core.graph.nodes import NodeBase, Question
from probative.core.graph.nodes import Source as SourceNode
from probative.extract.pipeline import extract_candidates
from probative.graph_runtime.state import GraphState, RunContext
from probative.ingest import _detect_format, ingest
from probative.ledger.build import claim_patch, source_node
from probative.ledger.classify import Classification, classify_source
from probative.ledger.contradict import contradiction_patch

HELD_OUT_TEMPLATE: Final = (
    "The source {path} was not added to the evidence: {reason}. Which tier and kind is it?"
)
JUDGED_FILE: Final = "judged_pairs.jsonl"
PROVISIONAL: Final = "claim confidence constants are provisional policy (OI38)"


class LedgerInput(BaseModel):
    max_pairs: int = 100


class EvidenceLedger:
    name = "evidence_ledger"
    input_model = LedgerInput
    output_model = AgentResult
    tools = ()
    tier_policy = TierPolicy(allowed=frozenset({Tier.T1}))

    def __init__(
        self,
        *,
        owner: str,
        max_pairs: int = 100,
        extra_sources: Sequence[CoreSource] = (),
    ) -> None:
        self._owner = owner
        self._max_pairs = max_pairs
        self._extra = tuple(extra_sources)

    def run(self, state: GraphState, ctx: RunContext) -> AgentResult:
        if ctx.provider is None:
            raise ValueError("EvidenceLedger needs a provider to extract claims")
        started = time.monotonic()
        now = ctx.clock()
        known = {n.sha256 for n in state.graph.nodes.values() if isinstance(n, SourceNode)}
        nodes: list[NodeBase] = []
        edges: list[Edge] = []
        unsure: list[str] = [PROVISIONAL]
        input_tokens = output_tokens = 0

        def hold_out(path: str, reason: str) -> None:
            nodes.append(
                Question.make(
                    text=HELD_OUT_TEMPLATE.format(path=path, reason=reason),
                    raised_by="gap",
                    owner=self._owner,
                    asserted_at=now,
                )
            )
            unsure.append(f"held out: {path} ({reason})")

        extractions: dict[str, ExtractionResult] = {}
        sources: list[CoreSource] = []
        root = ctx.source_root.resolve()
        spent = 0
        for path in _discover(ctx.source_root, ctx.run_dir):
            rel = path.relative_to(root).as_posix()
            try:
                fmt = _detect_format(path)
            except IngestError:
                continue  # not a document the ingester reads; not evidence
            if not path.resolve().is_relative_to(root):
                hold_out(rel, "it resolves to a file outside the source root")
                continue
            if ctx.budget.tokens_left - spent <= 0:
                hold_out(rel, "the token budget ran out before it was read")
                continue
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if sha in known:
                continue
            verdict = classify_source(rel, fmt)
            if not isinstance(verdict, Classification):
                hold_out(rel, verdict.reason)
                continue
            try:
                core = ingest(path, tier=verdict.tier, kind=verdict.kind)
            except IngestError as err:
                hold_out(rel, f"it could not be read ({type(err).__name__})")
                known.add(sha)
                continue
            known.add(sha)
            sources.append(core)
            extraction = extract_candidates(core, ctx.provider, model=ctx.model)
            spent += extraction.usage.input_tokens + extraction.usage.output_tokens
            extractions[core.id] = extraction
        sources.extend(s for s in self._extra if s.sha256 not in known)

        for core in sources:
            node = source_node(core, ctx.source_root, owner=self._owner, now=now)
            extraction = extractions.get(core.id) or extract_candidates(
                core, ctx.provider, model=ctx.model
            )
            input_tokens += extraction.usage.input_tokens
            output_tokens += extraction.usage.output_tokens
            built_nodes, built_edges = claim_patch(
                node, core, extraction, owner=self._owner, now=now
            )
            nodes.extend([node, *built_nodes])
            edges.extend(built_edges)

        # preview with the stored copy of any node already committed: a re-stated claim has
        # a computed confidence the agent's copy does not, and the graph refuses a mismatch
        preview = state.graph.with_patch(
            nodes=[state.graph.nodes.get(n.id, n) for n in nodes], edges=edges
        )
        cache = ctx.run_dir / JUDGED_FILE
        skip = _read_judged(cache, ctx.model)
        found = contradiction_patch(
            preview,
            ctx.provider,
            ctx.model,
            max_pairs=self._max_pairs,
            owner=self._owner,
            now=now,
            skip=skip,
            token_budget=max(0, ctx.budget.tokens_left - input_tokens - output_tokens),
        )
        _write_judged(cache, ctx.model, found.judged_pairs)
        input_tokens += found.usage.input_tokens
        output_tokens += found.usage.output_tokens
        if found.budget_stopped:
            unsure.append("the token budget ran out; some statements were not compared")
        if found.truncated:
            unsure.append("the pair limit was reached; some statements were not compared")
        return AgentResult(
            proposed_nodes=_unique([*nodes, *found.nodes]),
            proposed_edges=_unique_edges([*edges, *found.edges]),
            rationale="classified new sources, extracted claims, compared related statements",
            self_assessment=SelfAssessment(least_sure_about=tuple(unsure)),
            cost=CostRecord(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                wall_seconds=time.monotonic() - started,
            ),
        )


def _discover(root: Path, run_dir: Path) -> list[Path]:
    base, skip = root.resolve(), run_dir.resolve()
    found = []
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base)
        if not path.is_file() or any(p.startswith(".") for p in rel.parts):
            continue
        if path.resolve().is_relative_to(skip):
            continue
        found.append(path)
    return found


def _unique(nodes: list[NodeBase]) -> tuple[NodeBase, ...]:
    return tuple({n.id: n for n in nodes}.values())


def _unique_edges(edges: list[Edge]) -> tuple[Edge, ...]:
    return tuple({e.id: e for e in edges}.values())


def _read_judged(path: Path, model: str) -> frozenset[tuple[str, str]]:
    """Pairs already judged by this model on an earlier run. A cache in the run directory,
    not graph state: a verdict about two fixed statements stays true if a patch is rejected."""
    if not path.is_file():
        return frozenset()
    found: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("model") == model:
            found.add((str(row.get("a")), str(row.get("b"))))
    return frozenset(found)


def _write_judged(path: Path, model: str, pairs: Sequence[tuple[str, str]]) -> None:
    if not pairs:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for a, b in pairs:
            fh.write(json.dumps({"model": model, "a": a, "b": b}) + "\n")
