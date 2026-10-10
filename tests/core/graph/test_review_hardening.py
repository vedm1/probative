"""Findings from the checkpoint-A independent review (B1-B5, S1-S5, S8, N3, N5-N7).

Each test is a way someone could have forged, corrupted or silently weakened the
graph. They live together so the review's reach is visible in one place.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from probative.core.evidence import Locator
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph, GraphIntegrityError
from probative.core.graph.mirror import MirrorStaleError, load_mirror, rebuild_mirror
from probative.core.graph.nodes import (
    Claim,
    EvidenceSpan,
    Need,
    NodeBase,
    ProcessStep,
    Source,
    ValueProp,
)
from probative.core.graph.store import GraphFileError, content_hash, dumps, loads
from probative.core.graph.values import Computed, Input
from tests.core.graph._samples import ENV, T0, all_samples, conf, sample_claim, sample_span
from tests.core.graph.test_store import _full_graph

GOLDEN = Path(__file__).parent / "golden_ids.json"


# -- B1: a recomputed value must not re-id the node ----------------------------


def test_identity_is_authored_content_so_a_computed_value_does_not_change_the_id() -> None:
    a = Claim.make(text="x", tier="T1", confidence=conf(), **ENV)
    b = Claim.make(
        text="x",
        tier="T1",
        confidence=Computed(value=0.9, formula_id="confidence.v1", input_ids=[]),
        **ENV,
    )
    assert a.id == b.id


def test_a_differing_computed_value_is_a_conflict_not_a_silent_keep() -> None:
    a = Claim.make(text="x", tier="T1", confidence=conf(), **ENV)
    b = Claim.make(
        text="x",
        tier="T1",
        confidence=Computed(value=0.9, formula_id="confidence.v1", input_ids=[]),
        **ENV,
    )
    g = Graph.empty().with_patch(nodes=[a])
    with pytest.raises(GraphIntegrityError, match="different content"):
        g.with_patch(nodes=[b])


def test_golden_ids_pin_every_types_identity() -> None:
    ids = {t: n.id for t, n in sorted(all_samples().items())}
    if os.environ.get("UPDATE_GOLDEN_IDS") == "1":
        GOLDEN.write_text(json.dumps(ids, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert json.loads(GOLDEN.read_text(encoding="utf-8")) == ids, (
        "a node's identity changed: every stored id changes with it; bump SCHEMA_VERSION"
    )


# -- B2/B3: no forged node, edge or graph gets in -------------------------------


def test_with_patch_rejects_a_node_whose_content_no_longer_matches_its_id() -> None:
    forged = sample_claim().model_copy(update={"text": "forged"})
    with pytest.raises(GraphIntegrityError, match="derived"):
        Graph.empty().with_patch(nodes=[forged])


def test_with_patch_rejects_a_model_construct_node() -> None:
    sneaky = Need.model_construct(
        id="need_000000000000", type="need", partition="main", owner="o", asserted_at=T0, text="x"
    )
    with pytest.raises(GraphIntegrityError):
        Graph.empty().with_patch(nodes=[sneaky])


def test_with_patch_rejects_a_subclass_that_overrides_identity() -> None:
    class Collides(Need):
        def identity(self) -> object:
            return "same"

    with pytest.raises(GraphIntegrityError, match="class"):
        Graph.empty().with_patch(nodes=[Collides.make(text="a", **ENV)])


def test_a_node_class_without_a_type_cannot_be_built() -> None:
    with pytest.raises(ValidationError):
        NodeBase(id="foo_000000000000", owner="o", asserted_at=T0)


def test_with_patch_rejects_a_forged_edge() -> None:
    s = all_samples()
    good = Edge.make(
        type=EdgeType.EVIDENCED_BY, src=s["claim"].id, dst=s["evidence_span"].id, **ENV
    )
    forged = good.model_copy(update={"owner": "mallory"})
    g = Graph.empty().with_patch(nodes=[s["claim"], s["evidence_span"]])
    with pytest.raises(GraphIntegrityError):
        g.with_patch(edges=[forged.model_copy(update={"dst": s["claim"].id})])
    g.with_patch(edges=[good])


def test_a_forged_edge_that_passes_the_endpoint_rules_is_still_rejected() -> None:
    s = all_samples()
    other = sample_span(text="world!")
    good = Edge.make(
        type=EdgeType.EVIDENCED_BY, src=s["claim"].id, dst=s["evidence_span"].id, **ENV
    )
    retargeted = good.model_copy(update={"dst": other.id})  # valid pair, stale id
    g = Graph.empty().with_patch(nodes=[s["claim"], s["evidence_span"], other])
    with pytest.raises(GraphIntegrityError, match="derived"):
        g.with_patch(edges=[retargeted])


def test_the_graph_constructor_offers_no_unchecked_path() -> None:
    s = all_samples()
    bad = Edge.make(type=EdgeType.ADDRESSES, src=s["need"].id, dst=s["feature_idea"].id, **ENV)
    with pytest.raises(TypeError):
        Graph({s["need"].id: s["need"]}, {bad.id: bad})  # type: ignore[call-arg]
    assert len(Graph().nodes) == 0


# -- B4: tamper detection covers every field ------------------------------------


def _tamper(mutate) -> None:  # type: ignore[no-untyped-def]
    doc = json.loads(dumps(_full_graph()))
    mutate(doc)
    with pytest.raises(GraphFileError):
        loads(json.dumps(doc).encode())


def test_flipping_a_sources_tier_is_caught() -> None:
    def m(doc: dict) -> None:  # type: ignore[type-arg]
        for n in doc["nodes"]:
            if n["type"] == "source":
                n["tier"] = "T5"

    _tamper(m)


def test_editing_a_spans_text_or_locator_is_caught() -> None:
    def m(doc: dict) -> None:  # type: ignore[type-arg]
        for n in doc["nodes"]:
            if n["type"] == "evidence_span":
                n["text"] = "HELLO"
                n["locator"]["line"] = 99

    _tamper(m)


def test_editing_an_edges_owner_or_attrs_is_caught() -> None:
    def m(doc: dict) -> None:  # type: ignore[type-arg]
        doc["edges"][0]["owner"] = "mallory"
        doc["edges"][0]["attrs"] = {"reason": "zzz"}

    _tamper(m)


def test_editing_asserted_at_is_caught() -> None:
    def m(doc: dict) -> None:  # type: ignore[type-arg]
        doc["nodes"][0]["asserted_at"] = "2000-01-01T00:00:00Z"

    _tamper(m)


def test_the_file_records_a_content_hash_that_loads_verifies() -> None:
    g = _full_graph()
    doc = json.loads(dumps(g))
    assert doc["content_hash"] == content_hash(g)
    doc["content_hash"] = "0" * 64
    with pytest.raises(GraphFileError, match="hash"):
        loads(json.dumps(doc).encode())


# -- B5/S5: the mirror is verified row by row, and fails as MirrorStaleError ----


def _db(tmp_path: Path) -> tuple[Path, Graph]:
    g = _full_graph()
    db = tmp_path / "graph.sqlite"
    rebuild_mirror(g, db)
    return db, g


def _sql(db: Path, stmt: str) -> None:
    con = sqlite3.connect(db)
    try:
        with con:
            con.execute(stmt)
    finally:
        con.close()


def test_a_deleted_row_is_detected(tmp_path: Path) -> None:
    db, g = _db(tmp_path)
    _sql(db, "DELETE FROM nodes WHERE type = 'need'")
    with pytest.raises(MirrorStaleError):
        load_mirror(db, expected=g)


def test_an_extra_row_is_detected(tmp_path: Path) -> None:
    db, g = _db(tmp_path)
    extra = Need.make(text="smuggled", **ENV)
    _sql(
        db,
        f"INSERT INTO nodes VALUES ('{extra.id}', 'need', 'main', 'ved', NULL, "
        f"'{extra.model_dump_json()}')",
    )
    with pytest.raises(MirrorStaleError):
        load_mirror(db, expected=g)


def test_a_denormalised_column_that_disagrees_with_the_json_is_detected(tmp_path: Path) -> None:
    db, g = _db(tmp_path)
    _sql(db, "UPDATE nodes SET owner = 'mallory' WHERE type = 'need'")
    with pytest.raises(MirrorStaleError, match="column"):
        load_mirror(db, expected=g)


def test_a_missing_or_corrupt_mirror_is_stale_and_leaves_no_stray_file(tmp_path: Path) -> None:
    g = _full_graph()
    with pytest.raises(MirrorStaleError):
        load_mirror(tmp_path / "nope.sqlite", expected=g)
    assert list(tmp_path.iterdir()) == []
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"this is not a database")
    with pytest.raises(MirrorStaleError):
        load_mirror(bad, expected=g)


def test_rebuilding_into_a_new_directory_works(tmp_path: Path) -> None:
    rebuild_mirror(_full_graph(), tmp_path / "a" / "b" / "graph.sqlite")
    assert (tmp_path / "a" / "b" / "graph.sqlite").is_file()


# -- S1: nothing inside a frozen node can be mutated -----------------------------


def test_containers_inside_nodes_and_edges_are_immutable() -> None:
    c = sample_claim()
    with pytest.raises(AttributeError):
        c.confidence.input_ids.append("evil")  # type: ignore[attr-defined]
    e = Edge.make(
        type=EdgeType.SUPERSEDES, src="need_aaaaaaaaaaaa", dst="need_bbbbbbbbbbbb",
        attrs={"reason": "r"}, **ENV,
    )  # fmt: skip
    with pytest.raises(TypeError):
        e.attrs["reason"] = ""  # type: ignore[index]
    with pytest.raises(AttributeError):
        ValueProp.make(statement="s", refuses=["need_aaaaaaaaaaaa"], **ENV).refuses.append("x")  # type: ignore[attr-defined]
    step = ProcessStep.make(
        name="n", actor="a", metrics=[Input(value=1, unit="m", provenance="p")], **ENV
    )
    with pytest.raises(AttributeError):
        step.metrics.append(step.metrics[0])  # type: ignore[attr-defined]


def test_a_locator_inside_a_node_cannot_be_edited_in_place() -> None:
    span = sample_span()
    with pytest.raises(ValidationError):
        span.locator.page = 5
    loc = Locator(heading_path=["A", "B"])
    held = EvidenceSpan.make(
        source_ref=span.source_ref, start=0, end=5, text="hello", locator=loc, **ENV
    )
    loc.heading_path.append("C")  # type: ignore[union-attr]
    assert held.locator.heading_path == ("A", "B")
    assert held.id == EvidenceSpan.model_validate(held.model_dump()).id


# -- S2/S3: input ids look like ids; numbers are real numbers ----------------------


def test_computed_input_ids_must_look_like_ids() -> None:
    with pytest.raises(ValidationError):
        Computed(value=1.0, formula_id="f.v1", input_ids=["not an id"])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, "5"])
def test_input_values_must_be_finite_real_numbers(bad: object) -> None:
    with pytest.raises(ValidationError):
        Input(value=bad, unit="u", provenance="p")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "1"])
def test_computed_values_must_be_finite_real_numbers(bad: object) -> None:
    with pytest.raises(ValidationError):
        Computed(value=bad, formula_id="f.v1", input_ids=[])  # type: ignore[arg-type]


# -- S4: loads is strict about the file's shape -------------------------------------


def test_duplicate_node_entries_are_rejected() -> None:
    doc = json.loads(dumps(_full_graph()))
    dup = dict(doc["nodes"][0])
    dup["asserted_at"] = "2030-01-01T00:00:00Z"
    doc["nodes"].append(dup)
    with pytest.raises(GraphFileError, match="duplicate"):
        loads(json.dumps(doc).encode())


@pytest.mark.parametrize("version", ["0.1", "0.1.zzz", "0.1.0.1", ""])
def test_malformed_versions_are_rejected(version: str) -> None:
    doc = json.loads(dumps(Graph.empty()))
    doc["schema_version"] = version
    with pytest.raises(GraphFileError):
        loads(json.dumps(doc).encode())


def test_deeply_nested_input_is_a_graph_file_error() -> None:
    with pytest.raises(GraphFileError):
        loads(b"[" * 100000 + b"]" * 100000)


# -- S8: Source paths ------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "a\x00b",
        "./x",
        "a/./b",
        "~/x",
        "file:///etc/passwd",
        "a/ ..",
        ".. /x",
        "a//b",
        "x/",
        "C:foo",
    ],
)
def test_odd_source_paths_are_rejected(bad: str) -> None:
    base = all_samples()["source"].model_dump()
    with pytest.raises(ValidationError):
        Source.model_validate({**base, "path": bad})


def test_ordinary_nested_paths_are_fine() -> None:
    base = all_samples()["source"].model_dump(exclude={"id", "type"})
    assert Source.make(**{**base, "path": "interviews/2026 q3/call 1.md"}).path.endswith("1.md")


# -- N3: the same instant is the same bytes ----------------------------------------------


def test_asserted_at_is_normalised_to_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    a = Need.make(text="t", owner="o", asserted_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC))
    b = Need.make(text="t", owner="o", asserted_at=datetime(2026, 10, 1, 14, 30, tzinfo=ist))
    assert a == b and a.model_dump_json() == b.model_dump_json()
    assert dumps(Graph().with_patch(nodes=[a])) == dumps(Graph().with_patch(nodes=[b]))
