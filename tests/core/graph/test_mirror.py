from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from probative.core.graph.graph import Graph
from probative.core.graph.mirror import MirrorStaleError, load_mirror, rebuild_mirror
from probative.core.graph.store import dumps, write_graph
from tests.core.graph.test_store import _full_graph


def test_round_trip_through_the_mirror(tmp_path: Path) -> None:
    g = _full_graph()
    db = tmp_path / "graph.sqlite"
    rebuild_mirror(g, db)
    again = load_mirror(db, expected=g)
    assert again.nodes == g.nodes and again.edges == g.edges


def test_building_a_mirror_never_changes_graph_json(tmp_path: Path) -> None:
    g = _full_graph()
    path = tmp_path / "graph.json"
    write_graph(g, path)
    before = path.read_bytes()
    rebuild_mirror(g, tmp_path / "graph.sqlite")
    assert path.read_bytes() == before == dumps(g)


def test_rebuild_replaces_an_existing_mirror(tmp_path: Path) -> None:
    db = tmp_path / "graph.sqlite"
    rebuild_mirror(_full_graph(), db)
    rebuild_mirror(Graph.empty(), db)
    assert load_mirror(db, expected=Graph.empty()).nodes == {}


def test_a_stale_mirror_is_refused_not_silently_read(tmp_path: Path) -> None:
    db = tmp_path / "graph.sqlite"
    rebuild_mirror(Graph.empty(), db)
    with pytest.raises(MirrorStaleError, match="rebuild"):
        load_mirror(db, expected=_full_graph())


def test_the_mirror_is_indexed_for_querying(tmp_path: Path) -> None:
    db = tmp_path / "graph.sqlite"
    g = _full_graph()
    rebuild_mirror(g, db)
    with sqlite3.connect(db) as con:
        n = con.execute("SELECT count(*) FROM nodes WHERE type = 'need'").fetchone()[0]
        owners = {r[0] for r in con.execute("SELECT DISTINCT owner FROM nodes")}
        e = con.execute("SELECT count(*) FROM edges WHERE type = 'EVIDENCED_BY'").fetchone()[0]
        idx = {r[1] for r in con.execute("SELECT * FROM sqlite_master WHERE type = 'index'")}
    assert (n, owners, e) == (1, {"ved"}, 1)
    assert {"nodes_type", "nodes_partition_owner", "edges_src", "edges_dst"} <= idx


def test_superseded_by_is_a_column(tmp_path: Path) -> None:
    from probative.core.graph.edges import Edge, EdgeType
    from probative.core.graph.nodes import Need
    from tests.core.graph._samples import ENV

    v1, v2 = Need.make(text="v1", **ENV), Need.make(text="v2", **ENV)
    e = Edge.make(type=EdgeType.SUPERSEDES, src=v2.id, dst=v1.id, attrs={"reason": "r"}, **ENV)
    db = tmp_path / "g.sqlite"
    rebuild_mirror(Graph.empty().with_patch(nodes=[v1, v2], edges=[e]), db)
    with sqlite3.connect(db) as con:
        rows = dict(con.execute("SELECT id, superseded_by FROM nodes").fetchall())
    assert rows == {v1.id: v2.id, v2.id: None}
