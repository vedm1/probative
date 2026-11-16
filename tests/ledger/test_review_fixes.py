"""Defects found by the independent PB13 review (B1, B2, S1-S4, S6), each pinned."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import probative.formulas  # noqa: F401  (registers the formulas)
from probative.core.evidence import Tier
from probative.core.graph import store
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, Question
from probative.core.graph.nodes import Source as SourceNode
from probative.core.graph.validators import validate_graph
from probative.core.graph.values import Computed
from probative.formulas.validator import FormulaValidator
from probative.graph_runtime.budget import BudgetView
from probative.graph_runtime.modes import Mode
from probative.graph_runtime.phases import Phase
from probative.ledger.agent import EvidenceLedger
from probative.ledger.contradict import PairJudgement, PairVerdict, candidate_pairs
from probative.llm import FakeProvider, TokenUsage
from probative.llm.types import Message
from tests.graph_runtime._harness import phases
from tests.graph_runtime._support import clock, good_ratings
from tests.ledger import _corpus
from tests.ledger._helpers import NOW, OWNER, write
from tests.ledger.test_agent import context, state
from tests.ledger.test_end_to_end import final_graph

USAGE = TokenUsage(input_tokens=100, output_tokens=5)
SENT = "Approvals take three days or more."


def rt(root: Path, provider: FakeProvider):  # type: ignore[no-untyped-def]
    from probative.graph_runtime.runtime import Runtime

    return Runtime(
        root / "run1", source_root=root, mode=Mode.SOLO,
        agents={Phase.P0: EvidenceLedger(owner=OWNER)}, critics={},
        phases=phases(critics=frozenset()), clock=clock, provider=provider, model="m",
    )  # fmt: skip


def gen(text: str):  # type: ignore[no-untyped-def]
    from probative.extract.prompts import ConstraintOutput, GeneralOutput, RawQuote

    return [GeneralOutput(claims=[RawQuote(quote=text)]), ConstraintOutput()]


# -- B1: a new source repeating a committed statement ---------------------------


def test_b1_a_new_source_that_repeats_a_committed_statement_corroborates_it(tmp_path: Path) -> None:
    write(tmp_path, "interviews/a.md", SENT + "\n")
    first = rt(tmp_path, FakeProvider(gen(SENT), usage=USAGE))
    assert first.start(Phase.P0).status == "committed"
    first.close()
    write(tmp_path, "interviews/b.md", "# Second interview\n\n" + SENT + "\n")
    second = rt(tmp_path, FakeProvider(gen(SENT), usage=USAGE))
    assert second.start(Phase.P0, attempt=2).status == "committed"
    g = final_graph(tmp_path)
    (claim,) = [n for n in g.nodes.values() if isinstance(n, Claim)]
    assert claim.confidence.value == pytest.approx(0.75)


# -- B2: Claim.confidence may only name the claim confidence formulas -------------


def test_b2_a_claim_confidence_cannot_borrow_another_formula() -> None:
    imp, sat = good_ratings()
    ok = Claim.make(
        text="x y z", tier=Tier.T1,
        confidence=Computed(value=None, formula_id="gap", input_ids=[imp.id, sat.id]),
        owner=OWNER, asserted_at=NOW,
    )  # fmt: skip
    g = Graph.empty().with_patch(nodes=[imp, sat, ok])
    settled = FormulaValidator().settle(g)
    assert [v.code for v in FormulaValidator().check(settled)] == ["I4_FORMULA_BINDING"]
    assert settled.nodes[ok.id].confidence.value is None  # type: ignore[attr-defined]


# -- S1: superseding a source must not leave the graph unfixable -------------------


def test_s1_a_superseded_source_still_stands_behind_its_claim(tmp_path: Path) -> None:
    from tests.ledger.test_build import graph_of

    g, _ = graph_of(tmp_path, ("interviews/a.md", SENT + "\n", (SENT,)))
    old = next(n for n in g.nodes.values() if isinstance(n, SourceNode))
    new = SourceNode.make(
        sha256="b" * 64, ingest_id="src_" + "b" * 16, format=old.format, tier=old.tier,
        kind=old.kind, extractor=old.extractor, extractor_version=old.extractor_version,
        path="interviews/a2.md", owner=OWNER, asserted_at=NOW,
    )  # fmt: skip
    sup = Edge.make(type=EdgeType.SUPERSEDES, src=new.id, dst=old.id, attrs={"reason": "r"},
                    owner=OWNER, asserted_at=NOW)  # fmt: skip
    g = FormulaValidator().settle(g.with_patch(nodes=[new], edges=[sup]))
    assert FormulaValidator().check(g) == []
    assert validate_graph(g, source_root=tmp_path) == []


# -- S2 and S6: discovery ---------------------------------------------------------


def test_s2_a_symlink_out_of_the_root_is_held_out_and_never_read(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "secret.md"
    outside.write_text("Top secret statement here.\n")
    write(root, "interviews/a.md", SENT + "\n")
    (root / "interviews" / "link.md").symlink_to(outside)
    provider = FakeProvider([*gen(SENT)], usage=USAGE)
    result = EvidenceLedger(owner=OWNER).run(state(), context(root, provider))
    gaps = [
        n.text for n in result.proposed_nodes if isinstance(n, Question) and n.raised_by == "gap"
    ]
    assert any("interviews/link.md" in g and "outside" in g for g in gaps)
    assert not any("secret" in getattr(n, "text", "") for n in result.proposed_nodes)


def test_s6_only_documents_are_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path, "interviews/a.md", SENT + "\n")
    (tmp_path / "interviews" / "blob.bin").write_bytes(b"\x00" * 10)
    read: list[str] = []
    real = Path.read_bytes

    def spy(self: Path) -> bytes:
        read.append(self.name)
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    EvidenceLedger(owner=OWNER).run(
        state(), context(tmp_path, FakeProvider(gen(SENT), usage=USAGE))
    )
    assert "blob.bin" not in read


# -- S3: a judged pair is not judged again -------------------------------------------


def test_s3_a_consistent_pair_is_not_rejudged_on_the_next_run(tmp_path: Path) -> None:
    _corpus.build(tmp_path)
    script = [*_corpus.extraction_script(), PairJudgement(verdict=PairVerdict.CONSISTENT)]
    first = rt(tmp_path, FakeProvider(script, usage=USAGE))
    first.start(Phase.P0)
    first.close()
    write(tmp_path, "interviews/c.md", "Something unrelated entirely.\n")
    from probative.extract.prompts import ConstraintOutput, GeneralOutput

    second = rt(
        tmp_path, FakeProvider([GeneralOutput(), ConstraintOutput()], usage=USAGE)
    )  # fmt: skip  (no judge answer scripted: a call would fail)
    assert second.start(Phase.P0, attempt=2).status == "committed"


def test_s3_a_judged_pair_stays_candidate_unless_told_otherwise() -> None:
    from probative.ledger.build import new_claim

    a = new_claim("late approvals hurt", Tier.T1, None, owner=OWNER, now=NOW)
    b = new_claim("approvals hurt badly", Tier.T1, None, owner=OWNER, now=NOW)
    g = Graph.empty().with_patch(nodes=[a, b])
    pair = tuple(sorted((a.id, b.id)))
    assert len(candidate_pairs(g, 5).pairs) == 1
    assert candidate_pairs(g, 5, skip=frozenset({pair})).pairs == ()


# -- S4: the budget ----------------------------------------------------------------


def test_s4_an_exhausted_budget_stops_judging_and_says_so(tmp_path: Path) -> None:
    _corpus.build(tmp_path)
    ctx = context(tmp_path, FakeProvider([*_corpus.extraction_script()], usage=USAGE))
    tight = type(ctx)(**{**ctx.__dict__, "budget": BudgetView(tokens_left=1, seconds_left=100.0)})
    result = EvidenceLedger(owner=OWNER).run(state(), tight)
    assert any("budget" in s for s in result.self_assessment.least_sure_about)
    gaps = [
        n.text for n in result.proposed_nodes if isinstance(n, Question) and n.raised_by == "gap"
    ]
    assert any("budget" in g for g in gaps)
    assert isinstance(Message, type) and os.name  # keep imports honest
    assert store is not None
