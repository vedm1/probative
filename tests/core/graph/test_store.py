from __future__ import annotations

import json
import os
import random
from pathlib import Path

import pytest

from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.schema import SCHEMA_VERSION, schema_json
from probative.core.graph.store import (
    GraphFileError,
    content_hash,
    dumps,
    loads,
    read_graph,
    write_graph,
)
from tests.core.graph._samples import ENV, all_samples

SCHEMA_FILE = Path(__file__).parents[3] / "schemas" / f"graph-{SCHEMA_VERSION}.schema.json"


def _full_graph(order_seed: int | None = None) -> Graph:
    s = all_samples()
    nodes = list(s.values())
    edges = [
        Edge.make(type=EdgeType.EVIDENCED_BY, src=s["claim"].id, dst=s["evidence_span"].id, **ENV),
        Edge.make(type=EdgeType.TESTED_BY, src=s["hypothesis"].id, dst=s["test"].id, **ENV),
        Edge.make(type=EdgeType.ADDRESSES, src=s["feature_idea"].id, dst=s["need"].id, **ENV),
    ]
    if order_seed is not None:
        rng = random.Random(order_seed)
        rng.shuffle(nodes)
        rng.shuffle(edges)
    return Graph.empty().with_patch(nodes=nodes, edges=edges)


def test_round_trip_is_lossless_for_every_node_type() -> None:
    g = _full_graph()
    again = loads(dumps(g))
    assert again.nodes == g.nodes and again.edges == g.edges


def test_bytes_do_not_depend_on_insertion_order() -> None:
    assert dumps(_full_graph(1)) == dumps(_full_graph(2)) == dumps(_full_graph())


def test_serialisation_is_canonical() -> None:
    raw = dumps(_full_graph())
    assert raw.endswith(b"\n") and b"\r" not in raw
    doc = json.loads(raw)
    assert list(doc) == ["content_hash", "edges", "nodes", "schema_version"]
    ids = [n["id"] for n in doc["nodes"]]
    assert ids == sorted(ids)
    assert doc["schema_version"] == SCHEMA_VERSION


def test_content_hash_is_stable_and_sensitive() -> None:
    g = _full_graph()
    assert content_hash(g) == content_hash(_full_graph(3))
    smaller = Graph.empty().with_patch(nodes=[all_samples()["need"]])
    assert content_hash(smaller) != content_hash(g)


def test_write_is_atomic_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    g = _full_graph()
    write_graph(g, path)
    assert read_graph(path).nodes == g.nodes
    assert [p.name for p in tmp_path.iterdir()] == ["graph.json"]  # no temp file left
    write_graph(g, path)  # idempotent
    assert path.read_bytes() == dumps(g)


def test_unsupported_major_version_is_rejected() -> None:
    doc = json.loads(dumps(_full_graph()))
    doc["schema_version"] = "9.0.0"
    with pytest.raises(GraphFileError, match=r"9\.0\.0"):
        loads(json.dumps(doc).encode())


def test_a_newer_minor_version_is_rejected_rather_than_half_read() -> None:
    major, minor, patch = SCHEMA_VERSION.split(".")
    doc = json.loads(dumps(Graph.empty()))
    doc["schema_version"] = f"{major}.{int(minor) + 1}.{patch}"
    with pytest.raises(GraphFileError):
        loads(json.dumps(doc).encode())


def test_unknown_fields_and_malformed_input_are_rejected() -> None:
    doc = json.loads(dumps(_full_graph()))
    with pytest.raises(GraphFileError):
        loads(json.dumps({**doc, "extra": 1}).encode())
    doc["nodes"][0]["surprise"] = 1
    with pytest.raises(GraphFileError):
        loads(json.dumps(doc).encode())
    with pytest.raises(GraphFileError):
        loads(b"not json")


def test_a_tampered_node_is_caught_on_load() -> None:
    doc = json.loads(dumps(_full_graph()))
    for n in doc["nodes"]:
        if n["type"] == "claim":
            n["text"] = "tampered"
    with pytest.raises(GraphFileError, match="derived"):
        loads(json.dumps(doc).encode())


def test_integrity_is_rechecked_on_load() -> None:
    doc = json.loads(dumps(_full_graph()))
    doc["edges"][0]["dst"] = "evidence_span_ffffffffffff"
    with pytest.raises(GraphFileError):
        loads(json.dumps(doc).encode())


def test_the_committed_json_schema_is_the_generated_one() -> None:
    generated = schema_json()
    if os.environ.get("UPDATE_SCHEMA") == "1":
        SCHEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_FILE.write_text(generated, encoding="utf-8")
    assert SCHEMA_FILE.read_text(encoding="utf-8") == generated, (
        "graph schema changed: bump SCHEMA_VERSION and regenerate with UPDATE_SCHEMA=1"
    )


def test_the_schema_names_every_node_type_and_the_version() -> None:
    doc = json.loads(schema_json())
    assert SCHEMA_VERSION in doc["$id"]
    assert len(doc["properties"]["nodes"]["items"]["oneOf"]) == 43
