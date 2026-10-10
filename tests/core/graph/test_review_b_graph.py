"""Checkpoint-B review findings for the graph layer (S4, S5, S8, N5)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from probative.core.evidence import Locator, Tier
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph, GraphIntegrityError
from probative.core.graph.mirror import MirrorStaleError, load_mirror, rebuild_mirror
from probative.core.graph.nodes import Claim, EvidenceSpan, Source
from probative.core.graph.values import Computed
from tests.core.graph._samples import ENV, conf, sample_claim, sample_source
from tests.core.graph.test_store import _full_graph

# -- S4: every field outside the id can be revised, with SUPERSEDES --------------------------


def test_reclassifying_a_source_makes_a_new_node_that_can_supersede_the_old() -> None:
    old = sample_source()
    new = Source.make(**{**old.model_dump(exclude={"id", "type"}), "tier": Tier.T2})
    assert new.id != old.id
    e = Edge.make(
        type=EdgeType.SUPERSEDES, src=new.id, dst=old.id, attrs={"reason": "re-tiered"}, **ENV
    )
    g = Graph.empty().with_patch(nodes=[old, new], edges=[e])
    assert [n.id for n in g.current()] == [new.id]


def test_a_corrected_locator_is_a_new_span_not_a_conflict() -> None:
    src = sample_source()
    a = EvidenceSpan.make(
        source_ref=src.id, start=0, end=5, text="hello", locator=Locator(line=1), **ENV
    )
    b = EvidenceSpan.make(
        source_ref=src.id, start=0, end=5, text="hello", locator=Locator(line=2), **ENV
    )
    assert a.id != b.id
    Graph.empty().with_patch(nodes=[src, a, b])


def test_a_renamed_or_re_extracted_source_is_a_different_node() -> None:
    old = sample_source()
    base = old.model_dump(exclude={"id", "type"})
    assert Source.make(**{**base, "path": "other.md"}).id != old.id
    assert Source.make(**{**base, "extractor_version": "md/2"}).id != old.id


# -- the sanctioned way to change a Computed value ---------------------------------------------


def _recomputed(value: float) -> Computed:
    return Computed(value=value, formula_id="confidence.v1", input_ids=[])


def test_with_recomputed_replaces_a_computed_value_and_keeps_every_id_and_edge() -> None:
    g = _full_graph()
    claim = next(n for n in g.nodes.values() if isinstance(n, Claim))
    g2 = g.with_recomputed({claim.id: {"confidence": _recomputed(0.9)}})
    new = g2.nodes[claim.id]
    assert isinstance(new, Claim) and new.confidence.value == 0.9
    assert new.id == claim.id and g2.edges == g.edges
    assert g.nodes[claim.id] == claim  # the original is untouched


def test_with_recomputed_only_touches_computed_fields_of_known_nodes() -> None:
    g = _full_graph()
    claim = next(n for n in g.nodes.values() if isinstance(n, Claim))
    with pytest.raises(GraphIntegrityError, match="Computed"):
        g.with_recomputed({claim.id: {"text": "changed"}})  # type: ignore[dict-item]
    with pytest.raises(GraphIntegrityError, match="unknown"):
        g.with_recomputed({"claim_ffffffffffff": {"confidence": _recomputed(0.1)}})
    with pytest.raises(GraphIntegrityError, match="no field"):
        g.with_recomputed({claim.id: {"nonsense": _recomputed(0.1)}})


def test_with_patch_still_refuses_a_silent_computed_change() -> None:
    a = sample_claim()
    b = Claim.make(text=a.text, tier=a.tier, confidence=_recomputed(0.99), **ENV)
    assert a.id == b.id
    with pytest.raises(GraphIntegrityError, match="different content"):
        Graph.empty().with_patch(nodes=[a]).with_patch(nodes=[b])


# -- S5: the mirror's edge columns and node id column are verified -----------------------------


def _mirror(tmp_path: Path) -> tuple[Path, Graph]:
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


@pytest.mark.parametrize(
    "stmt",
    [
        "UPDATE edges SET src = 'claim_ffffffffffff'",
        "UPDATE edges SET dst = 'claim_ffffffffffff'",
        "UPDATE edges SET type = 'REQUIRES'",
        "UPDATE edges SET id = 'edge_ffffffffffff' WHERE type = 'EVIDENCED_BY'",
        "UPDATE nodes SET id = 'need_ffffffffffff' WHERE type = 'need'",
    ],
)
def test_a_tampered_edge_or_id_column_is_a_stale_mirror(tmp_path: Path, stmt: str) -> None:
    db, g = _mirror(tmp_path)
    _sql(db, stmt)
    with pytest.raises(MirrorStaleError):
        load_mirror(db, expected=g)


# -- S8 / N5: Source ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["meeting 10:30.txt", "ab:c.md", "notes (v2).md", "dir/x y.md"])
def test_legal_posix_names_are_accepted(name: str) -> None:
    base = sample_source().model_dump(exclude={"id", "type"})
    assert Source.make(**{**base, "path": name}).path == name


@pytest.mark.parametrize("bad", ["a::b.md", "http://x/y", "Z:\\x", "d:y.md"])
def test_drive_letters_and_schemes_are_still_rejected(bad: str) -> None:
    base = sample_source().model_dump(exclude={"id", "type"})
    with pytest.raises(ValidationError):
        Source.make(**{**base, "path": bad})


def test_ingest_id_must_be_the_one_ingest_derives_from_the_bytes() -> None:
    base = sample_source().model_dump(exclude={"id", "type"})
    assert base["ingest_id"] == f"src_{base['sha256'][:16]}"
    with pytest.raises(ValidationError, match="ingest_id"):
        Source.make(**{**base, "ingest_id": "src_0000000000000000"})


def test_unused_imports_are_not_hiding() -> None:
    assert conf().formula_id and Edge and Tier
