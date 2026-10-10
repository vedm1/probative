"""The graph container.

A `Graph` is immutable: the only way to get a different one is
`with_patch(nodes, edges)`, which returns a new graph or raises. There is no
update or delete, so "agents never mutate the graph" holds by construction and
revision is `SUPERSEDES` (I7). Structural integrity (dangling ends, endpoint
types, supersession shape) is a construction error; *invariant* violations
(I1, I2, ...) are `validate_graph`'s job, so a patch can be judged before commit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Self

from pydantic import ValidationError

from probative.core.graph.edges import Edge, EdgeType, check_endpoints
from probative.core.graph.nodes import NODE_CLASSES, NodeBase
from probative.core.graph.values import Computed


class GraphIntegrityError(ValueError):
    """The patch would leave the graph structurally unsound."""


def _verify_node(node: NodeBase) -> None:
    """A node reaches the graph only if it is exactly what its class would build
    from its own content. `model_copy(update=...)`, `model_construct` and
    subclasses that bend `identity()` all fail here, not later on `loads`."""
    kind = getattr(node, "type", None)
    cls = NODE_CLASSES.get(kind) if isinstance(kind, str) else None
    if cls is None or type(node) is not cls:
        raise GraphIntegrityError(f"{type(node).__name__} is not a registered node class")
    try:
        cls.model_validate(node.model_dump())
    except ValidationError as err:
        raise GraphIntegrityError(f"{node.id}: {err}") from err


def _verify_edge(edge: Edge) -> None:
    if type(edge) is not Edge:
        raise GraphIntegrityError(f"{type(edge).__name__} is not an Edge")
    try:
        Edge.model_validate(edge.model_dump())
    except ValidationError as err:
        raise GraphIntegrityError(f"{edge.id}: {err}") from err


def _same_but_when(a: NodeBase | Edge, b: NodeBase | Edge) -> bool:
    return a.model_dump(exclude={"asserted_at"}) == b.model_dump(exclude={"asserted_at"})


class Graph:
    def __init__(self) -> None:
        """An empty graph. The only way to a populated one is `with_patch`."""
        self._fill({}, {})

    @classmethod
    def _built(cls, nodes: dict[str, NodeBase], edges: dict[str, Edge]) -> Graph:
        graph = cls()
        graph._fill(nodes, edges)
        return graph

    def _fill(self, nodes: dict[str, NodeBase], edges: dict[str, Edge]) -> None:
        self._nodes: dict[str, NodeBase] = nodes
        self._edges: dict[str, Edge] = edges
        self._out: dict[str, list[Edge]] = {}
        self._in: dict[str, list[Edge]] = {}
        self._successor: dict[str, str] = {}
        self._predecessor: dict[str, str] = {}
        for edge in sorted(self._edges.values(), key=lambda e: e.id):
            self._out.setdefault(edge.src, []).append(edge)
            self._in.setdefault(edge.dst, []).append(edge)
            if edge.type is EdgeType.SUPERSEDES:
                self._successor[edge.dst] = edge.src
                self._predecessor[edge.src] = edge.dst

    @classmethod
    def empty(cls) -> Self:
        return cls()

    @property
    def nodes(self) -> Mapping[str, NodeBase]:
        return MappingProxyType(self._nodes)

    @property
    def edges(self) -> Mapping[str, Edge]:
        return MappingProxyType(self._edges)

    # -- reads ---------------------------------------------------------------

    def out_edges(self, node_id: str, type: EdgeType | None = None) -> list[Edge]:
        return [e for e in self._out.get(node_id, []) if type is None or e.type is type]

    def in_edges(self, node_id: str, type: EdgeType | None = None) -> list[Edge]:
        return [e for e in self._in.get(node_id, []) if type is None or e.type is type]

    def superseded_by(self, node_id: str) -> str | None:
        return self._successor.get(node_id)

    def current(self) -> list[NodeBase]:
        """Nodes nothing supersedes: what is believed now."""
        return [n for i, n in sorted(self._nodes.items()) if i not in self._successor]

    def history(self, node_id: str) -> list[str]:
        """The chain of revisions this node belongs to, oldest first."""
        first = node_id
        while first in self._predecessor:
            first = self._predecessor[first]
        chain = [first]
        while chain[-1] in self._successor:
            chain.append(self._successor[chain[-1]])
        return chain

    # -- the only way to change anything: a new graph --------------------------

    def with_recomputed(self, updates: Mapping[str, Mapping[str, Computed]]) -> Graph:
        """A new graph in which named `Computed` fields hold new values.

        This is the one sanctioned way a stored value changes without a
        revision: a `Computed` value is derived from the rest of the graph, so
        it is not part of a node's identity, and recomputing it (PB11's
        `FormulaValidator`, PB12's `Committer`) must neither re-id the node nor
        orphan its edges. Nothing else about a node can change this way, and
        no agent calls it.
        """
        nodes = dict(self._nodes)
        for node_id, fields in updates.items():
            node = nodes.get(node_id)
            if node is None:
                raise _recompute_error(f"unknown node {node_id}")
            declared = type(node).model_fields
            for name, value in fields.items():
                if name not in declared:
                    raise _recompute_error(f"{type(node).__name__} has no field {name}")
                if declared[name].annotation is not Computed or not isinstance(value, Computed):
                    raise _recompute_error(f"{name} is not a Computed field")
            changed = node.model_copy(update=dict(fields))
            _verify_node(changed)
            nodes[node_id] = changed
        return Graph._built(nodes, dict(self._edges))

    def with_patch(self, nodes: Iterable[NodeBase] = (), edges: Iterable[Edge] = ()) -> Graph:
        merged_nodes = dict(self._nodes)
        for node in nodes:
            known = merged_nodes.get(node.id)
            if known is None:
                _verify_node(node)
                merged_nodes[node.id] = node
            elif not _same_but_when(known, node):
                raise GraphIntegrityError(f"node {node.id} already exists with different content")
        merged_edges = dict(self._edges)
        for edge in edges:
            known_edge = merged_edges.get(edge.id)
            if known_edge is not None:
                if not _same_but_when(known_edge, edge):
                    raise GraphIntegrityError(f"edge {edge.id} already exists with different attrs")
                continue
            _verify_edge(edge)
            for end in (edge.src, edge.dst):
                if end not in merged_nodes:
                    raise GraphIntegrityError(f"{edge.type.name} {edge.id}: dangling end {end}")
            try:
                check_endpoints(edge, merged_nodes[edge.src], merged_nodes[edge.dst])
            except ValueError as err:
                raise GraphIntegrityError(str(err)) from err
            merged_edges[edge.id] = edge
        _check_supersession(merged_edges.values())
        return Graph._built(merged_nodes, merged_edges)


def _recompute_error(msg: str) -> GraphIntegrityError:
    return GraphIntegrityError(f"with_recomputed: {msg}")


def _check_supersession(edges: Iterable[Edge]) -> None:
    successor: dict[str, str] = {}
    predecessor: dict[str, str] = {}
    for edge in sorted(edges, key=lambda e: e.id):
        if edge.type is not EdgeType.SUPERSEDES:
            continue
        new, old = edge.src, edge.dst
        if new == old:
            raise GraphIntegrityError(f"{new} cannot supersede itself")
        if successor.get(old, new) != new:
            raise GraphIntegrityError(f"{old} would be superseded more than once")
        if predecessor.get(new, old) != old:
            raise GraphIntegrityError(f"{new} would supersede more than one node")
        successor[old] = new
        predecessor[new] = old
    for start in successor:
        seen = {start}
        node = start
        while node in successor:
            node = successor[node]
            if node in seen:
                raise GraphIntegrityError(f"supersession cycle through {node}")
            seen.add(node)
