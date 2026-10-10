"""The `graph.json` JSON Schema, versioned independently of the tool (§6.3).

`SCHEMA_VERSION` changes when the file format changes, not when probative does.
Before 1.0 every minor bump may break readers; a reader accepts the same
`major.minor` only. The generated schema is committed under `schemas/` and a
test fails if the two disagree, so a schema change is always deliberate.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from probative.core.graph.edges import Edge
from probative.core.graph.nodes import Node

SCHEMA_VERSION = "0.1.0"


class GraphFile(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Probative graph")

    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    nodes: list[Node]
    edges: list[Edge]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def schema_json() -> str:
    doc = GraphFile.model_json_schema()
    doc["$id"] = f"urn:probative:graph-schema:{SCHEMA_VERSION}"
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
