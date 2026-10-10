"""Canonical `graph.json` (§6.3): deterministic bytes, so diffs and hashes mean something.

The file records a `content_hash` over its own nodes and edges, and `loads`
recomputes it. That catches an edit to *any* field, including the ones outside
a node's identity (a `Source`'s tier, a span's text, an edge's owner), unless the
editor also rewrites the hash. It is an integrity check against accident and
sloppy hand-edits, not a signature; git history is the audit trail.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from probative.core.graph.graph import Graph, GraphIntegrityError
from probative.core.graph.schema import SCHEMA_VERSION, GraphFile

_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class GraphFileError(Exception):
    """`graph.json` cannot be read as this version of the schema."""


def _body(graph: Graph) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "nodes": [n.model_dump(mode="json") for _, n in sorted(graph.nodes.items())],
        "edges": [e.model_dump(mode="json") for _, e in sorted(graph.edges.items())],
    }


def _canonical(doc: dict[str, Any]) -> bytes:
    text = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return (text + "\n").encode("utf-8")


def content_hash(graph: Graph) -> str:
    return hashlib.sha256(_canonical(_body(graph))).hexdigest()


def dumps(graph: Graph) -> bytes:
    body = _body(graph)
    body["content_hash"] = hashlib.sha256(_canonical(body)).hexdigest()
    return _canonical(body)


def _series(version: str) -> str:
    return ".".join(version.split(".")[:2])


def loads(raw: bytes) -> Graph:
    try:
        doc = json.loads(raw)
    except (ValueError, RecursionError) as err:
        raise GraphFileError(f"not readable JSON: {err}") from err
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if (
        not isinstance(version, str)
        or not _VERSION.match(version)
        or _series(version) != _series(SCHEMA_VERSION)
    ):
        raise GraphFileError(
            f"graph schema version {version!r} is not readable by schema {SCHEMA_VERSION}"
        )
    try:
        parsed = GraphFile.model_validate(doc)
        for kind, ids in (
            ("node", [n.id for n in parsed.nodes]),
            ("edge", [e.id for e in parsed.edges]),
        ):
            if len(set(ids)) != len(ids):
                raise GraphFileError(f"duplicate {kind} id in the file")
        graph = Graph.empty().with_patch(nodes=parsed.nodes, edges=parsed.edges)
    except (ValidationError, GraphIntegrityError, RecursionError) as err:
        raise GraphFileError(str(err)) from err
    if content_hash(graph) != parsed.content_hash:
        raise GraphFileError("the file's content hash does not match its nodes and edges")
    return graph


def write_graph(graph: Graph, path: Path) -> None:
    """Temp file + `os.replace`: a reader never sees half a graph."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".graph-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(dumps(graph))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_graph(path: Path) -> Graph:
    return loads(path.read_bytes())
