"""Checkpoint-B review findings for validators.py (B3, S1-S3, N8)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from probative.core.evidence import IngestError, SourceFormat, Tier
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, Source
from probative.core.graph.nodes import Test as _TestNode
from probative.core.graph.validators import validate_graph
from probative.core.graph.values import Input
from tests.core.graph._real import grounded_graph, ingest_as
from tests.core.graph._samples import ENV, T0, conf, sample_claim, sample_hypothesis, sample_source
from tests.core.graph._samples import sample_test as _sample_test

FIX = Path(__file__).parents[2] / "fixtures"


def codes(vs) -> set[str]:  # type: ignore[no-untyped-def]
    return {v.code for v in vs}


def edge(kind: EdgeType, src: str, dst: str) -> Edge:
    return Edge.make(type=kind, src=src, dst=dst, **ENV)


def _phrase(path: Path, fmt: SourceFormat | None) -> str:
    text = ingest_as(path, fmt, Tier.T1).text
    return next(line.strip() for line in text.splitlines() if len(line.strip()) > 12)[:40]


FORMATS = [
    ("tracker/jira_all_fields.csv", SourceFormat.JIRA_CSV),
    ("tracker/ado_issues.csv", SourceFormat.ADO_CSV),
    ("tracker/jira_issues.html", SourceFormat.JIRA_HTML),
    ("tracker/jira_export.xml", SourceFormat.JIRA_XML),
    ("confluence/page_export.doc", SourceFormat.CONFLUENCE_WORD),
]


@pytest.mark.parametrize(("rel", "fmt"), FORMATS)
def test_evidence_from_every_ingest_format_validates(
    tmp_path: Path, rel: str, fmt: SourceFormat
) -> None:
    name = Path(rel).name
    shutil.copy(FIX / rel, tmp_path / name)
    graph, *_ = grounded_graph(tmp_path, name, _phrase(tmp_path / name, fmt), fmt=fmt)
    assert validate_graph(graph, source_root=tmp_path) == []


@pytest.mark.parametrize(("rel", "fmt"), FORMATS)
def test_tampered_tracker_or_confluence_evidence_is_still_caught(
    tmp_path: Path, rel: str, fmt: SourceFormat
) -> None:
    name = Path(rel).name
    shutil.copy(FIX / rel, tmp_path / name)
    _, source, span, claim = grounded_graph(tmp_path, name, _phrase(tmp_path / name, fmt), fmt=fmt)
    shifted = EvidenceSpan.make(
        source_ref=source.id, start=span.start + 1, end=span.end + 1, text=span.text,
        locator=span.locator, **ENV,
    )  # fmt: skip
    bad = Graph.empty().with_patch(
        nodes=[source, shifted, claim], edges=[edge(EdgeType.EVIDENCED_BY, claim.id, shifted.id)]
    )
    assert codes(validate_graph(bad, source_root=tmp_path)) == {"I1_SPAN_MISMATCH"}


# -- S1: never crash, never leak an absolute path ----------------------------------


def _with_path(graph: Graph, source: Source, path: str) -> Graph:
    base = source.model_dump(exclude={"id", "type"})
    moved = Source.make(**{**base, "path": path})
    spans = [n for n in graph.nodes.values() if isinstance(n, EvidenceSpan)]
    claim = next(n for n in graph.nodes.values() if isinstance(n, Claim))
    new_span = EvidenceSpan.make(
        **{**spans[0].model_dump(exclude={"id", "type"}), "source_ref": moved.id}
    )
    return Graph.empty().with_patch(
        nodes=[moved, new_span, claim], edges=[edge(EdgeType.EVIDENCED_BY, claim.id, new_span.id)]
    )


def test_an_overlong_path_is_a_violation_not_a_crash(tmp_path: Path) -> None:
    shutil.copy(FIX / "ingest" / "notes.md", tmp_path / "notes.md")
    graph, source, *_ = grounded_graph(tmp_path, "notes.md", "The scope is deliberately narrow.")
    bad = _with_path(graph, source, "a" * 300 + ".md")
    assert codes(validate_graph(bad, source_root=tmp_path)) == {"I1_SPAN_UNRESOLVED"}


def test_an_unreadable_file_is_a_violation_not_a_crash(tmp_path: Path) -> None:
    shutil.copy(FIX / "ingest" / "notes.md", tmp_path / "notes.md")
    graph, *_ = grounded_graph(tmp_path, "notes.md", "The scope is deliberately narrow.")
    os.chmod(tmp_path / "notes.md", 0)
    try:
        if os.access(tmp_path / "notes.md", os.R_OK):
            pytest.skip("running as a user that can read mode 0 files")
        assert codes(validate_graph(graph, source_root=tmp_path)) == {"I1_SPAN_UNRESOLVED"}
    finally:
        os.chmod(tmp_path / "notes.md", 0o644)


def test_messages_never_contain_the_absolute_source_root(tmp_path: Path) -> None:
    shutil.copy(FIX / "ingest" / "notes.md", tmp_path / "notes.md")
    graph, source, *_ = grounded_graph(tmp_path, "notes.md", "The scope is deliberately narrow.")
    (tmp_path / "notes.md").write_text("# changed\n", encoding="utf-8")
    stale = Source.make(
        **{**source.model_dump(exclude={"id", "type"}), "extractor_version": "md/0"}
    )
    for g in (graph, _with_path(graph, source, "gone.md"), _with_path(graph, stale, "notes.md")):
        for v in validate_graph(g, source_root=tmp_path):
            assert str(tmp_path) not in v.message and "/private" not in v.message


# -- S2: I2 -------------------------------------------------------------------------


def _test_with(**changes: object) -> list[str]:
    hyp = sample_hypothesis()
    base = _sample_test().model_dump(exclude={"id", "type"})
    test = _TestNode.make(**{**base, **changes})
    g = Graph.empty().with_patch(
        nodes=[hyp, test], edges=[edge(EdgeType.TESTED_BY, hyp.id, test.id)]
    )
    return [v.code for v in validate_graph(g, source_root=Path("."))]


@pytest.mark.parametrize("status", ["running", "passed", "killed"])
def test_a_test_that_has_run_must_say_when_it_started(status: str) -> None:
    assert _test_with(status=status, started_at=None) == ["I2_TEST_INCOMPLETE"]
    assert _test_with(status=status, started_at=T0.replace(hour=11)) == []


def test_a_planned_test_needs_no_start() -> None:
    assert _test_with(status="planned", started_at=None) == []


@pytest.mark.parametrize("blank", ["\u200b", "\u00a0", "\u2003\u200d", "\ufeff"])
def test_invisible_text_is_blank(blank: str) -> None:
    assert _test_with(method=blank) == ["I2_TEST_INCOMPLETE"]
    assert _test_with(kill_criterion=blank) == ["I2_TEST_INCOMPLETE"]


def test_cost_and_duration_must_be_stated_sensibly() -> None:
    bad_cost = Input(value=-5, unit="days", provenance="p")
    zero = Input(value=0, unit="days", provenance="p")
    free = Input(value=0, unit="days", provenance="p")
    assert _test_with(cost=bad_cost) == ["I2_TEST_INCOMPLETE"]
    assert _test_with(duration=zero) == ["I2_TEST_INCOMPLETE"]
    assert _test_with(cost=free) == []  # a free test is a test


# -- S3: simulated evidence is quarantined (DESIGN 5.5) --------------------------------


def _t5_source_graph(claim_tier: Tier) -> tuple[Graph, Claim]:
    base = sample_source().model_dump(exclude={"id", "type"})
    src = Source.make(**{**base, "tier": Tier.T5})
    span = EvidenceSpan.make(source_ref=src.id, start=0, end=5, text="hello", locator={}, **ENV)
    claim = Claim.make(text="sim", tier=claim_tier, confidence=conf(), **ENV)
    g = Graph.empty().with_patch(
        nodes=[src, span, claim], edges=[edge(EdgeType.EVIDENCED_BY, claim.id, span.id)]
    )
    return g, claim


@pytest.mark.parametrize("tier", [Tier.T1, Tier.T2, Tier.T3, Tier.T4])
def test_t5_evidence_cannot_ground_a_stronger_claim(tier: Tier, tmp_path: Path) -> None:
    g, claim = _t5_source_graph(tier)
    found = [v for v in validate_graph(g, source_root=tmp_path) if v.invariant == "I1"]
    assert ("I1_TIER_MISMATCH", claim.id) in {(v.code, v.node_id) for v in found}


def test_a_t4_claim_derived_from_a_t5_claim_is_not_grounded(tmp_path: Path) -> None:
    g, sim = _t5_source_graph(Tier.T5)
    t4 = sample_claim("inferred", Tier.T4)
    g = g.with_patch(nodes=[t4], edges=[edge(EdgeType.DERIVED_FROM, t4.id, sim.id)])
    assert ("I1_ORPHAN_CLAIM", t4.id) in {
        (v.code, v.node_id) for v in validate_graph(g, source_root=tmp_path)
    }


def test_a_t5_claim_on_a_t5_source_is_consistent(tmp_path: Path) -> None:
    g, claim = _t5_source_graph(Tier.T5)
    assert not [v for v in validate_graph(g, source_root=tmp_path) if v.node_id == claim.id]


# -- N8: pin rules the first review found unpinned -----------------------------------------


def test_one_grounded_parent_is_enough_for_a_t4_claim(tmp_path: Path) -> None:
    shutil.copy(FIX / "ingest" / "notes.md", tmp_path / "notes.md")
    graph, _, _, good = grounded_graph(tmp_path, "notes.md", "The scope is deliberately narrow.")
    orphan = sample_claim("orphan parent")
    t4 = sample_claim("inferred", Tier.T4)
    g = graph.with_patch(
        nodes=[orphan, t4],
        edges=[
            edge(EdgeType.DERIVED_FROM, t4.id, good.id),
            edge(EdgeType.DERIVED_FROM, t4.id, orphan.id),
        ],
    )
    assert {(v.code, v.node_id) for v in validate_graph(g, source_root=tmp_path)} == {
        ("I1_ORPHAN_CLAIM", orphan.id)
    }


def test_a_claim_with_two_mismatched_sources_is_reported_once(tmp_path: Path) -> None:
    shutil.copy(FIX / "ingest" / "notes.md", tmp_path / "notes.md")
    graph, source, span, _ = grounded_graph(
        tmp_path, "notes.md", "The scope is deliberately narrow."
    )
    other = EvidenceSpan.make(
        source_ref=source.id, start=0, end=5, text="# Int", locator=span.locator, **ENV
    )
    over = Claim.make(text="x", tier=Tier.T2, confidence=conf(), **ENV)
    g = graph.with_patch(
        nodes=[other, over],
        edges=[
            edge(EdgeType.EVIDENCED_BY, over.id, span.id),
            edge(EdgeType.EVIDENCED_BY, over.id, other.id),
        ],
    )
    assert [v.code for v in validate_graph(g, source_root=tmp_path) if v.node_id == over.id] == [
        "I1_TIER_MISMATCH"
    ]


@pytest.mark.parametrize(
    "make_error", [lambda p: OSError(f"boom {p}"), lambda p: IngestError(p, "bad")]
)
def test_a_failing_re_extraction_is_a_violation_that_does_not_leak_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_error
) -> None:  # type: ignore[no-untyped-def]
    import probative.core.graph.validators as mod

    shutil.copy(FIX / "ingest" / "notes.md", tmp_path / "notes.md")
    graph, *_ = grounded_graph(tmp_path, "notes.md", "The scope is deliberately narrow.")

    def failing(source, span):  # type: ignore[no-untyped-def]
        raise make_error(source.path)

    monkeypatch.setattr(mod, "_reextractor", lambda fmt: failing)
    (v,) = validate_graph(graph, source_root=tmp_path)
    assert v.code == "I1_SPAN_UNRESOLVED"
    assert str(tmp_path) not in v.message and "boom" not in v.message
