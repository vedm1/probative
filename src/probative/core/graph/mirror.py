"""The SQLite mirror (§6.3): derived, disposable, gitignored.

Schema-agnostic on purpose: one row per node and per edge with the queryable
columns split out and the full JSON kept alongside, so a new node type needs no
migration. `graph.json` is the record; the mirror is rebuilt from it and refuses
to be read if its recorded hash no longer matches.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from probative.core.graph.edges import Edge
from probative.core.graph.graph import Graph, GraphIntegrityError
from probative.core.graph.nodes import Node, NodeBase
from probative.core.graph.store import content_hash

_DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE nodes (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, partition TEXT NOT NULL, owner TEXT NOT NULL,
  superseded_by TEXT, json TEXT NOT NULL
);
CREATE TABLE edges (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL,
  json TEXT NOT NULL
);
CREATE INDEX nodes_type ON nodes(type);
CREATE INDEX nodes_partition_owner ON nodes(partition, owner);
CREATE INDEX edges_src ON edges(src, type);
CREATE INDEX edges_dst ON edges(dst, type);
"""


class MirrorStaleError(Exception):
    """The mirror was built from a different graph. Rebuild it."""


def rebuild_mirror(graph: Graph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mirror-", suffix=".tmp")
    os.close(fd)
    try:
        with closing(sqlite3.connect(tmp)) as con, con:
            con.executescript(_DDL)
            con.execute("INSERT INTO meta VALUES ('graph_hash', ?)", (content_hash(graph),))
            con.executemany(
                "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        n.id,
                        n.type_name(),
                        n.partition,
                        n.owner,
                        graph.superseded_by(n.id),
                        n.model_dump_json(),
                    )
                    for n in graph.nodes.values()
                ],
            )
            con.executemany(
                "INSERT INTO edges VALUES (?, ?, ?, ?, ?)",
                [
                    (e.id, e.type.value, e.src, e.dst, e.model_dump_json())
                    for e in graph.edges.values()
                ],
            )
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_mirror(path: Path, *, expected: Graph) -> Graph:
    """Read a mirror back, to *verify* it against the graph it should mirror.

    `expected` is required: the mirror is never a source of truth. Every row is
    rebuilt into a graph that must equal `expected`, and every denormalised
    column must agree with the JSON beside it, so a deleted, added or edited row
    is refused rather than returned.
    """
    if not path.is_file():
        raise MirrorStaleError(f"{path} does not exist; rebuild it")
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as con:
            row = con.execute("SELECT value FROM meta WHERE key = 'graph_hash'").fetchone()
            node_rows = con.execute(
                "SELECT id, type, partition, owner, superseded_by, json FROM nodes"
            ).fetchall()
            edge_rows = con.execute("SELECT id, type, src, dst, json FROM edges").fetchall()
        node_adapter: TypeAdapter[NodeBase] = TypeAdapter(Node)
        nodes = [node_adapter.validate_json(r[5]) for r in node_rows]
        edges = [Edge.model_validate_json(r[4]) for r in edge_rows]
        result = Graph.empty().with_patch(nodes=nodes, edges=edges)
    except (sqlite3.DatabaseError, ValidationError, GraphIntegrityError) as err:
        raise MirrorStaleError(f"{path} is not a readable mirror ({err}); rebuild it") from err
    if row is None or row[0] != content_hash(expected) or content_hash(result) != row[0]:
        raise MirrorStaleError(f"{path} does not match graph.json; rebuild it")
    for row, node in zip(node_rows, nodes, strict=True):
        want = (
            node.id,
            node.type_name(),
            node.partition,
            node.owner,
            result.superseded_by(node.id),
        )
        if tuple(row[:5]) != want:
            raise MirrorStaleError(f"{path}: a column of node {node.id} disagrees with its JSON")
    for erow, edge in zip(edge_rows, edges, strict=True):
        if tuple(erow[:4]) != (edge.id, edge.type.value, edge.src, edge.dst):
            raise MirrorStaleError(f"{path}: a column of edge {edge.id} disagrees with its JSON")
    return result
