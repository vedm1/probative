from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from probative.core.evidence import Tier
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, Source
from probative.core.graph.nodes import Test as _TestNode
from probative.core.graph.validators import Violation, unverified_computed, validate_graph
from probative.core.graph.values import Computed
from tests.core.graph._real import grounded_graph
from tests.core.graph._samples import ENV, T0, T1, conf, sample_claim, sample_hypothesis
from tests.core.graph._samples import sample_test as _sample_test

FIXTURES = Path(__file__).parents[2] / "fixtures" / "ingest"
PHRASE = "The scope is deliberately narrow."


def codes(vs: list[Violation]) -> set[str]:
    return {v.code for v in vs}


def edge(kind: EdgeType, src: str, dst: str) -> Edge:
    return Edge.make(type=kind, src=src, dst=dst, **ENV)


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    shutil.copy(FIXTURES / "notes.md", tmp_path / "notes.md")
    return tmp_path


# -- I1 ----------------------------------------------------------------------


def test_a_grounded_claim_with_a_real_span_is_clean(run_dir: Path) -> None:
    graph, *_ = grounded_graph(run_dir, "notes.md", PHRASE)
    assert validate_graph(graph, source_root=run_dir) == []


def test_a_claim_with_no_evidence_is_a_violation_not_a_warning(run_dir: Path) -> None:
    claim = sample_claim()
    graph = Graph.empty().with_patch(nodes=[claim])
    (v,) = validate_graph(graph, source_root=run_dir)
    assert (v.invariant, v.code, v.node_id) == ("I1", "I1_ORPHAN_CLAIM", claim.id)


def test_a_hypothesis_needs_no_evidence_for_i1(run_dir: Path) -> None:
    hyp, test = sample_hypothesis(), _sample_test()
    graph = Graph.empty().with_patch(
        nodes=[hyp, test], edges=[edge(EdgeType.TESTED_BY, hyp.id, test.id)]
    )
    assert validate_graph(graph, source_root=run_dir) == []


def test_there_is_no_third_category(run_dir: Path) -> None:
    # a claim that merely says it is a hypothesis in its text, or sits next to a
    # hypothesis, is still an orphan
    hyp = sample_hypothesis("Users want X")
    claim = sample_claim("Users want X")
    graph = Graph.empty().with_patch(nodes=[hyp, claim])
    assert [
        v.code for v in validate_graph(graph, source_root=run_dir) if v.node_id == claim.id
    ] == ["I1_ORPHAN_CLAIM"]


def test_a_tampered_span_offset_fails(run_dir: Path) -> None:
    _, source, span, claim = grounded_graph(run_dir, "notes.md", PHRASE)
    shifted = EvidenceSpan.make(
        source_ref=source.id,
        start=span.start + 1,
        end=span.end + 1,
        text=span.text,
        locator=span.locator,
        **ENV,
    )
    bad = Graph.empty().with_patch(
        nodes=[source, shifted, claim], edges=[edge(EdgeType.EVIDENCED_BY, claim.id, shifted.id)]
    )
    (v,) = validate_graph(bad, source_root=run_dir)
    assert (v.code, v.node_id) == ("I1_SPAN_MISMATCH", shifted.id)


def test_a_span_whose_recorded_text_differs_fails(run_dir: Path) -> None:
    _, source, span, claim = grounded_graph(run_dir, "notes.md", PHRASE)
    forged = EvidenceSpan.make(
        source_ref=source.id,
        start=span.start,
        end=span.end,
        text="X" * len(span.text),
        locator=span.locator,
        **ENV,
    )
    bad = Graph.empty().with_patch(
        nodes=[source, forged, claim], edges=[edge(EdgeType.EVIDENCED_BY, claim.id, forged.id)]
    )
    assert codes(validate_graph(bad, source_root=run_dir)) == {"I1_SPAN_MISMATCH"}


def test_an_edited_source_file_fails_with_its_own_code(run_dir: Path) -> None:
    graph, *_ = grounded_graph(run_dir, "notes.md", PHRASE)
    (run_dir / "notes.md").write_text("# Different\n\nentirely\n", encoding="utf-8")
    assert codes(validate_graph(graph, source_root=run_dir)) == {"I1_SOURCE_CHANGED"}


def test_a_missing_source_file_is_unresolved(run_dir: Path) -> None:
    graph, *_ = grounded_graph(run_dir, "notes.md", PHRASE)
    (run_dir / "notes.md").unlink()
    assert codes(validate_graph(graph, source_root=run_dir)) == {"I1_SPAN_UNRESOLVED"}


def test_a_changed_normalisation_version_fails_with_its_own_code(run_dir: Path) -> None:
    _, source, span, claim = grounded_graph(run_dir, "notes.md", PHRASE)
    old = Source.make(**{**source.model_dump(exclude={"id", "type"}), "extractor_version": "md/0"})
    old_span = EvidenceSpan.make(
        **{**span.model_dump(exclude={"id", "type"}), "source_ref": old.id}
    )
    bad = Graph.empty().with_patch(
        nodes=[old, old_span, claim], edges=[edge(EdgeType.EVIDENCED_BY, claim.id, old_span.id)]
    )
    assert codes(validate_graph(bad, source_root=run_dir)) == {"I1_STALE_NORMALISATION"}


def test_a_span_with_no_source_node_is_unresolved(run_dir: Path) -> None:
    _, _source, span, claim = grounded_graph(run_dir, "notes.md", PHRASE)
    bad = Graph.empty().with_patch(
        nodes=[span, claim], edges=[edge(EdgeType.EVIDENCED_BY, claim.id, span.id)]
    )
    assert codes(validate_graph(bad, source_root=run_dir)) == {"I1_SPAN_UNRESOLVED"}


def test_a_source_path_escaping_the_root_through_a_symlink_is_unresolved(
    run_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    graph, *_ = grounded_graph(run_dir, "notes.md", PHRASE)
    outside = tmp_path_factory.mktemp("outside")
    shutil.copy(FIXTURES / "notes.md", outside / "notes.md")
    (run_dir / "notes.md").unlink()
    (run_dir / "notes.md").symlink_to(outside / "notes.md")
    assert codes(validate_graph(graph, source_root=run_dir)) == {"I1_SPAN_UNRESOLVED"}


def test_many_spans_in_one_source_reextract_it_once(
    run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import probative.core.graph.validators as mod

    graph, *_ = grounded_graph(run_dir, "notes.md", PHRASE)
    calls = []
    real = mod.reextract
    monkeypatch.setattr(mod, "reextract", lambda s, sp: calls.append(1) or real(s, sp))
    validate_graph(graph, source_root=run_dir)
    assert len(calls) == 1


def test_two_spans_of_one_source_are_each_checked_against_the_one_re_extraction(
    run_dir: Path,
) -> None:
    graph, source, first, _ = grounded_graph(run_dir, "notes.md", PHRASE)
    text = (run_dir / "notes.md").read_text(encoding="utf-8")
    late = "Images are out of scope."
    at = text.index(late)
    good = EvidenceSpan.make(
        source_ref=source.id, start=at, end=at + len(late), text=late, locator=first.locator, **ENV
    )
    off = EvidenceSpan.make(
        source_ref=source.id,
        start=at + 1,
        end=at + 1 + len(late),
        text=late,
        locator=first.locator,
        **ENV,
    )
    both = graph.with_patch(nodes=[good])
    assert validate_graph(both, source_root=run_dir) == []
    bad = both.with_patch(nodes=[off])
    assert [(v.code, v.node_id) for v in validate_graph(bad, source_root=run_dir)] == [
        ("I1_SPAN_MISMATCH", off.id)
    ]


def test_claim_tier_must_match_its_sources_tier(run_dir: Path) -> None:
    graph, _, span, _ = grounded_graph(run_dir, "notes.md", PHRASE)
    over = Claim.make(text=PHRASE, tier=Tier.T2, confidence=conf(), **ENV)  # source is T1
    bad = graph.with_patch(nodes=[over], edges=[edge(EdgeType.EVIDENCED_BY, over.id, span.id)])
    assert [(v.code, v.node_id) for v in validate_graph(bad, source_root=run_dir)] == [
        ("I1_TIER_MISMATCH", over.id)
    ]


def test_a_t4_claim_must_not_be_a_leaf(run_dir: Path) -> None:
    t4 = sample_claim("Inferred", tier=Tier.T4)
    graph = Graph.empty().with_patch(nodes=[t4])
    assert codes(validate_graph(graph, source_root=run_dir)) == {"I1_T4_LEAF"}


def test_a_t4_claim_derived_from_a_grounded_claim_is_clean(run_dir: Path) -> None:
    graph, _, _, claim = grounded_graph(run_dir, "notes.md", PHRASE)
    t4 = sample_claim("Inferred", tier=Tier.T4)
    g = graph.with_patch(nodes=[t4], edges=[edge(EdgeType.DERIVED_FROM, t4.id, claim.id)])
    assert validate_graph(g, source_root=run_dir) == []


def test_a_t4_claim_derived_only_from_an_orphan_is_still_an_orphan(run_dir: Path) -> None:
    parent = sample_claim("parent")
    t4 = sample_claim("Inferred", tier=Tier.T4)
    g = Graph.empty().with_patch(
        nodes=[parent, t4], edges=[edge(EdgeType.DERIVED_FROM, t4.id, parent.id)]
    )
    assert {(v.code, v.node_id) for v in validate_graph(g, source_root=run_dir)} == {
        ("I1_ORPHAN_CLAIM", parent.id),
        ("I1_ORPHAN_CLAIM", t4.id),
    }


def test_derivation_cycles_do_not_hang_or_ground_a_claim(run_dir: Path) -> None:
    a, b = sample_claim("a", Tier.T4), sample_claim("b", Tier.T4)
    g = Graph.empty().with_patch(
        nodes=[a, b],
        edges=[edge(EdgeType.DERIVED_FROM, a.id, b.id), edge(EdgeType.DERIVED_FROM, b.id, a.id)],
    )
    assert codes(validate_graph(g, source_root=run_dir)) == {"I1_ORPHAN_CLAIM"}


# -- I2 ----------------------------------------------------------------------


def test_a_hypothesis_without_a_test_is_a_violation(run_dir: Path) -> None:
    hyp = sample_hypothesis()
    (v,) = validate_graph(Graph.empty().with_patch(nodes=[hyp]), source_root=run_dir)
    assert (v.invariant, v.code, v.node_id) == ("I2", "I2_NO_TEST", hyp.id)


def test_a_complete_test_is_clean(run_dir: Path) -> None:
    hyp, test = sample_hypothesis(), _sample_test()
    g = Graph.empty().with_patch(
        nodes=[hyp, test], edges=[edge(EdgeType.TESTED_BY, hyp.id, test.id)]
    )
    assert validate_graph(g, source_root=run_dir) == []


@pytest.mark.parametrize("field", ["method", "kill_criterion"])
@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_a_test_with_a_blank_method_or_kill_criterion_is_incomplete(
    run_dir: Path, field: str, blank: str
) -> None:
    hyp = sample_hypothesis()
    base = _sample_test().model_dump(exclude={"id", "type"})
    test = _TestNode.make(**{**base, field: blank})
    g = Graph.empty().with_patch(
        nodes=[hyp, test], edges=[edge(EdgeType.TESTED_BY, hyp.id, test.id)]
    )
    assert [(v.code, v.node_id) for v in validate_graph(g, source_root=run_dir)] == [
        ("I2_TEST_INCOMPLETE", test.id)
    ]


def test_the_kill_criterion_must_be_recorded_before_the_test_starts(run_dir: Path) -> None:
    hyp = sample_hypothesis()
    base = _sample_test().model_dump(exclude={"id", "type"})
    late = _TestNode.make(
        **{**base, "criterion_recorded_at": T1, "started_at": T0, "status": "running"}
    )
    ok = _TestNode.make(
        **{**base, "criterion_recorded_at": T0, "started_at": T1, "status": "running"}
    )
    for test, want in ((late, ["I2_CRITERION_AFTER_START"]), (ok, [])):
        g = Graph.empty().with_patch(
            nodes=[hyp, test], edges=[edge(EdgeType.TESTED_BY, hyp.id, test.id)]
        )
        assert [v.code for v in validate_graph(g, source_root=run_dir)] == want


def test_a_criterion_recorded_at_the_same_instant_as_the_start_is_not_before(run_dir: Path) -> None:
    hyp = sample_hypothesis()
    base = _sample_test().model_dump(exclude={"id", "type"})
    test = _TestNode.make(
        **{**base, "criterion_recorded_at": T0, "started_at": T0, "status": "running"}
    )
    g = Graph.empty().with_patch(
        nodes=[hyp, test], edges=[edge(EdgeType.TESTED_BY, hyp.id, test.id)]
    )
    assert validate_graph(g, source_root=run_dir) == []  # recorded_at <= started_at


# -- I4 declaration shape (recomputation is PB11) ---------------------------


def test_computed_fields_are_listed_as_unverified_until_a_formula_is_registered() -> None:
    claim = sample_claim()
    g = Graph.empty().with_patch(nodes=[claim])
    assert unverified_computed(g) == [(claim.id, "confidence", "confidence.v1")]


def test_a_computed_input_that_names_no_node_is_a_violation(run_dir: Path) -> None:
    from probative.core.graph.nodes import Opportunity

    opp = Opportunity.make(
        value=Computed(value=1.0, formula_id="f.v1", input_ids=["rating_ffffffffffff"]), **ENV
    )
    g = Graph.empty().with_patch(nodes=[opp])
    (v,) = validate_graph(g, source_root=run_dir)
    assert (v.invariant, v.code) == ("I4", "I4_DANGLING_INPUT")


def test_violations_are_deterministic_and_ordered(run_dir: Path) -> None:
    nodes = [sample_claim(f"c{i}") for i in range(5)] + [sample_hypothesis("h")]
    g = Graph.empty().with_patch(nodes=nodes)
    first = validate_graph(g, source_root=run_dir)
    assert first == validate_graph(g, source_root=run_dir)
    assert first == sorted(first, key=lambda v: (v.invariant, v.code, v.node_id))
