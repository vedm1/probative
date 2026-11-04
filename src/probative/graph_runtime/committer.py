"""The Committer: the only thing that turns a patch into graph state (S1).

Agents propose; this disposes. A patch is judged as one unit and commits whole
or not at all. The order is fixed (cheap before costly, PB12 spec D1-D3):

1. every `Computed` an agent proposes must be `value=None` (I4: an agent never
   produces an output); a number it supplied is `I4_AGENT_VALUE`, even a right one;
2. the patch must fit the agent's tier policy;
3. `Graph.with_patch` (structure: dangling ends, endpoint types, supersession);
4. `FormulaValidator.recompute` fills the numbers, `Graph.with_recomputed` stores
   them (ids unchanged);
5. **`validate_graph` and `FormulaValidator.check` together** on the whole
   resulting graph (OI36b). There is no allow-list: until PB13 registers a
   confidence formula, a `Claim` cannot commit (OI34, D2);
6. the I7 variance hook, synchronously, before anything is written;
7. `graph.json`, the mirror, then the ledger line.

A `block` finding can never be committed over. A `warn` or `note` that names a
node becomes a `Finding` node with a `FLAGGED_BY` edge in the same commit (D6).
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from probative.agents.contract import TierPolicy
from probative.core.critic import Finding, Severity
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph, GraphIntegrityError
from probative.core.graph.mirror import MirrorStaleError, load_mirror, rebuild_mirror
from probative.core.graph.nodes import Finding as FindingNode
from probative.core.graph.nodes import NodeBase
from probative.core.graph.store import content_hash, read_graph, write_graph
from probative.core.graph.validators import Violation, validate_graph
from probative.core.graph.values import Computed
from probative.formulas.registry import REGISTRY, Registry
from probative.formulas.validator import FormulaValidator
from probative.graph_runtime.patch import Patch
from probative.graph_runtime.runfiles import RunFiles, append_jsonl, read_jsonl


class VarianceHook(Protocol):
    """I7: every commit computes variance against every live baseline,
    synchronously. PB27 supplies the real one; raising vetoes the commit."""

    def on_commit(self, before: Graph, after: Graph, patch: Patch) -> None: ...


class NoVariance:
    def on_commit(self, before: Graph, after: Graph, patch: Patch) -> None:
        return None


class CommitRejectedError(Exception):
    def __init__(self, violations: Sequence[Violation]) -> None:
        self.violations = tuple(violations)
        shown = "; ".join(f"{v.code} {v.node_id}" for v in self.violations[:5])
        super().__init__(f"{len(self.violations)} violation(s): {shown}")


@dataclass(frozen=True)
class Judgement:
    graph_after: Graph | None
    violations: tuple[Violation, ...]


@dataclass(frozen=True)
class CommitResult:
    graph: Graph
    content_hash: str
    finding_nodes: tuple[FindingNode, ...]


RESERVED_NODE_TYPES = frozenset({"finding", "baseline", "variance", "decision"})
"""Nodes only the machinery may write: a critic's finding (the Committer adds them), a
baseline (I7, PB27), a variance, and a person's decision. An agent that proposed one
could forge a verdict or a sign-off. A later phase that must write one lifts it here."""


def _computed_names(node: NodeBase) -> list[str]:
    return [n for n, f in type(node).model_fields.items() if f.annotation is Computed]


def _sorted(violations: Sequence[Violation]) -> tuple[Violation, ...]:
    unique = {(v.invariant, v.code, v.node_id, v.message): v for v in violations}
    return tuple(unique[k] for k in sorted(unique))


class Committer:
    def __init__(
        self,
        files: RunFiles,
        *,
        source_root: Path,
        clock: Callable[[], datetime],
        registry: Registry = REGISTRY,
        variance: VarianceHook | None = None,
    ) -> None:
        self._files = files
        self._source_root = source_root
        self._clock = clock
        self._registry = registry
        self._variance: VarianceHook = variance or NoVariance()

    # -- judging -------------------------------------------------------------

    def verify_clean(self, graph: Graph) -> list[Violation]:
        """Both validators, on a graph as it stands. A run refuses to start from
        a graph that is not clean (D2)."""
        found = [
            *validate_graph(graph, source_root=self._source_root),
            *FormulaValidator(self._registry).check(graph),
        ]
        return list(_sorted(found))

    def judge(
        self,
        graph: Graph,
        patch: Patch,
        *,
        policy: TierPolicy,
        extra_nodes: Sequence[NodeBase] = (),
        extra_edges: Sequence[Edge] = (),
    ) -> Judgement:
        """Judge a patch without side effect."""
        found: list[Violation] = []
        # A node already in the graph is that node: its id is derived from its content,
        # so the stored copy is the same node with its numbers filled in. Using it keeps
        # a re-commit harmless and stops a re-proposed node from changing a stored number.
        proposed = [graph.nodes.get(n.id, n) for n in patch.result.proposed_nodes]
        for node in proposed:
            if node.id in graph.nodes:
                continue
            if node.type_name() in RESERVED_NODE_TYPES:
                found.append(
                    Violation(
                        "S1",
                        "RESERVED_NODE",
                        node.id,
                        f"an agent may not propose a {node.type_name()} node",
                    )
                )
            for name in _computed_names(node):
                if getattr(node, name).value is not None:
                    found.append(
                        Violation(
                            "I4",
                            "I4_AGENT_VALUE",
                            node.id,
                            f"{type(node).__name__}.{name} arrived with a value; an agent "
                            "proposes inputs and leaves outputs to the formula",
                        )
                    )
            tier = getattr(node, "tier", None)
            if tier is not None and tier not in policy.allowed:
                found.append(
                    Violation(
                        "S1",
                        "TIER_POLICY",
                        node.id,
                        f"{type(node).__name__} rests on {tier}, outside the agent's tier policy",
                    )
                )
        try:
            candidate = graph.with_patch(
                nodes=[*proposed, *extra_nodes],
                edges=[*patch.result.proposed_edges, *extra_edges],
            )
            fixes = FormulaValidator(self._registry).recompute(candidate)
            if fixes:
                candidate = candidate.with_recomputed(fixes)
        except GraphIntegrityError as err:
            found.append(Violation("STRUCT", "STRUCTURE", "patch", str(err)))
            return Judgement(None, _sorted(found))
        found.extend(self.verify_clean(candidate))
        violations = _sorted(found)
        return Judgement(None if violations else candidate, violations)

    # -- committing ----------------------------------------------------------

    def commit(
        self,
        graph: Graph,
        patch: Patch,
        findings: Sequence[Finding],
        *,
        policy: TierPolicy,
    ) -> CommitResult:
        blocking = [f for f in findings if f.severity is Severity.BLOCK]
        if blocking:
            raise CommitRejectedError(
                [
                    Violation(
                        f.invariant or "CRITIC",
                        "BLOCKING_FINDING",
                        f.target_id or "patch",
                        f"{f.critic_id}/{f.check_id}: {f.message}",
                    )
                    for f in blocking
                ]
            )
        patch_ids = {n.id for n in patch.result.proposed_nodes}
        nodes, edges = self._finding_nodes(graph, patch_ids, findings)
        judged = self.judge(graph, patch, policy=policy, extra_nodes=nodes, extra_edges=edges)
        if judged.graph_after is None:
            raise CommitRejectedError(judged.violations)
        after = judged.graph_after
        try:
            self._variance.on_commit(graph, after, patch)
        except Exception as err:
            raise CommitRejectedError(
                [Violation("I7", "VARIANCE", "patch", f"{type(err).__name__}: {err}")]
            ) from err
        write_graph(after, self._files.graph_path)
        digest = content_hash(after)
        append_jsonl(
            self._files.ledger_path,
            {
                "kind": "commit",
                "patch_id": patch.id,
                "agent": patch.agent,
                "phase": patch.phase.value,
                "cycle": patch.cycle,
                "before_hash": content_hash(graph),
                "after_hash": digest,
                "findings": [
                    {
                        "critic_id": f.critic_id,
                        "check_id": f.check_id,
                        "severity": f.severity.value,
                        "target_id": f.target_id,
                    }
                    for f in findings
                ],
                "cost": patch.result.cost.model_dump(mode="json"),
                "committed_at": self._now().isoformat(),
            },
        )
        # The mirror is derived and disposable: last, and its failure cannot undo a commit.
        # `reconcile` rebuilds it.
        with contextlib.suppress(OSError, sqlite3.Error):
            rebuild_mirror(after, self._files.mirror_path)
        return CommitResult(after, digest, tuple(nodes))

    def reconcile(self) -> Graph:
        """After a crash the graph on disk can be ahead of the ledger. Append a
        `recovered` line so the audit trail says so; do nothing if they agree."""
        if not self._files.graph_path.is_file():
            return Graph.empty()
        graph = read_graph(self._files.graph_path)
        digest = content_hash(graph)
        lines = read_jsonl(self._files.ledger_path)
        last = lines[-1]["after_hash"] if lines else None
        try:
            load_mirror(self._files.mirror_path, expected=graph)
        except MirrorStaleError:
            rebuild_mirror(graph, self._files.mirror_path)
        if last != digest:
            append_jsonl(
                self._files.ledger_path,
                {
                    "kind": "recovered",
                    "before_hash": last,
                    "after_hash": digest,
                    "committed_at": self._now().isoformat(),
                },
            )
        return graph

    # -- helpers -------------------------------------------------------------

    def _now(self) -> datetime:
        return self._clock()

    def _finding_nodes(
        self, graph: Graph, patch_ids: set[str], findings: Sequence[Finding]
    ) -> tuple[list[FindingNode], list[Edge]]:
        nodes: dict[str, FindingNode] = {}
        edges: dict[str, Edge] = {}
        for f in findings:
            if f.target_id is None or (
                f.target_id not in graph.nodes and f.target_id not in patch_ids
            ):
                continue
            owner = f"critic:{f.critic_id}"
            node = FindingNode.make(
                critic_id=f.critic_id,
                check_id=f.check_id,
                severity=f.severity,
                invariant=f.invariant,
                message=f.message,
                remedy=f.remedy,
                target_id=f.target_id,
                owner=owner,
                asserted_at=self._now(),
            )
            nodes[node.id] = node
            edge = Edge.make(
                type=EdgeType.FLAGGED_BY,
                src=f.target_id,
                dst=node.id,
                owner=owner,
                asserted_at=self._now(),
            )
            edges[edge.id] = edge
        return list(nodes.values()), list(edges.values())
