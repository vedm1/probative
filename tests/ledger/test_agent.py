"""PB13: the `EvidenceLedger` agent, with a scripted provider (no key, no network)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import probative.formulas  # noqa: F401  (registers the formulas)
from probative.agents.contract import AgentResult
from probative.core.evidence import Tier
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, Question
from probative.core.graph.nodes import Source as SourceNode
from probative.graph_runtime.budget import BudgetView
from probative.graph_runtime.modes import Mode
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.state import GraphState, RunContext
from probative.graph_runtime.tedium import InteractionLog
from probative.ledger.agent import HELD_OUT_TEMPLATE, EvidenceLedger
from probative.ledger.contradict import PairJudgement, PairVerdict
from probative.llm import FakeProvider, TokenUsage
from tests.ledger import _corpus
from tests.ledger._helpers import NOW

USAGE = TokenUsage(input_tokens=100, output_tokens=5)


def context(root: Path, provider: FakeProvider | None) -> RunContext:
    return RunContext(
        provider=provider,
        model="test-model",
        run_dir=root / "run1",
        source_root=root,
        clock=lambda: NOW,
        budget=BudgetView(tokens_left=200_000, seconds_left=1800.0),
        interactions=InteractionLog(root / "run1" / "interactions.jsonl"),
    )


def state(graph: Graph | None = None) -> GraphState:
    return GraphState(graph=graph or Graph.empty(), phase=Phase.P0, mode=Mode.SOLO, cycle=1)


def scripted(*judge: PairVerdict) -> FakeProvider:
    return FakeProvider(
        [*_corpus.extraction_script(), *(PairJudgement(verdict=v) for v in judge)], usage=USAGE
    )


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    _corpus.build(tmp_path)
    return tmp_path


def run(root: Path, *judge: PairVerdict) -> AgentResult:
    return EvidenceLedger(owner="ved").run(state(), context(root, scripted(*judge)))


def test_the_agent_is_a_t1_producer_with_a_name() -> None:
    agent = EvidenceLedger(owner="ved")
    assert agent.name == "evidence_ledger"
    assert agent.tier_policy.allowed == frozenset({Tier.T1})


def test_it_proposes_sources_spans_and_claims_from_classified_files(corpus: Path) -> None:
    result = run(corpus, PairVerdict.CONTRADICTS)
    paths = sorted(n.path for n in result.proposed_nodes if isinstance(n, SourceNode))
    assert paths == sorted(_corpus.CLAIMS)
    assert len([n for n in result.proposed_nodes if isinstance(n, EvidenceSpan)]) == 6
    texts = sorted(n.text for n in result.proposed_nodes if isinstance(n, Claim))
    assert texts == sorted({q for qs in _corpus._claims_all() for q in qs})


def test_it_never_supplies_a_number(corpus: Path) -> None:
    result = run(corpus, PairVerdict.CONTRADICTS)
    claims = [n for n in result.proposed_nodes if isinstance(n, Claim)]
    assert claims and all(c.confidence.value is None for c in claims)
    assert all(c.confidence.formula_id == "claim_confidence_direct" for c in claims)


def test_an_unclassified_file_is_held_out_with_a_templated_question(corpus: Path) -> None:
    result = run(corpus, PairVerdict.CONSISTENT)
    gaps = sorted(
        n.text for n in result.proposed_nodes if isinstance(n, Question) and n.raised_by == "gap"
    )
    assert len(gaps) == 2
    for rel in _corpus.HELD_OUT:
        assert any(
            g.startswith(HELD_OUT_TEMPLATE.format(path=rel, reason="")[:30]) and rel in g
            for g in gaps
        )
    sources = {n.path for n in result.proposed_nodes if isinstance(n, SourceNode)}
    assert not set(_corpus.HELD_OUT) & sources
    assert any("held out: misc/notes.md" in s for s in result.self_assessment.least_sure_about)


def test_a_disagreement_becomes_one_question_and_two_links(corpus: Path) -> None:
    result = run(corpus, PairVerdict.CONTRADICTS)
    kinds = sorted(e.type.value for e in result.proposed_edges)
    assert kinds.count("CONTRADICTS") == 1 and kinds.count("RAISED_ABOUT") == 2
    (q,) = [
        n
        for n in result.proposed_nodes
        if isinstance(n, Question) and n.raised_by == "contradiction"
    ]
    assert "interviews/b.md" in q.text


def test_cost_is_the_providers_own_usage(corpus: Path) -> None:
    result = run(corpus, PairVerdict.CONSISTENT)
    calls = 4 * 2 + 1  # four ingested files, two passes each, and one judged pair
    assert result.cost.input_tokens == calls * USAGE.input_tokens
    assert result.cost.output_tokens == calls * USAGE.output_tokens


def test_the_run_directory_and_hidden_files_are_not_evidence(corpus: Path) -> None:
    (corpus / "run1").mkdir(exist_ok=True)
    (corpus / "run1" / "interviews.md").write_text("Not evidence at all.\n")
    (corpus / ".hidden").mkdir()
    (corpus / ".hidden" / "x.md").write_text("Hidden.\n")
    result = run(corpus, PairVerdict.CONSISTENT)
    assert not any(isinstance(n, SourceNode) and "run1" in n.path for n in result.proposed_nodes)
    assert not any(isinstance(n, SourceNode) and ".hidden" in n.path for n in result.proposed_nodes)


def test_it_refuses_to_run_without_a_provider(corpus: Path) -> None:
    with pytest.raises(ValueError, match="provider"):
        EvidenceLedger(owner="ved").run(state(), context(corpus, None))


def test_an_unreadable_file_is_held_out_not_fatal(corpus: Path) -> None:
    (corpus / "interviews" / "empty.md").write_bytes(b"")
    result = run(corpus, PairVerdict.CONSISTENT)
    gaps = [
        n.text for n in result.proposed_nodes if isinstance(n, Question) and n.raised_by == "gap"
    ]
    assert any("interviews/empty.md" in g and "EmptySourceError" in g for g in gaps)


def test_a_file_that_is_not_a_document_is_ignored(corpus: Path) -> None:
    (corpus / "interviews" / "photo.xyz").write_bytes(b"\x00\x01")
    result = run(corpus, PairVerdict.CONSISTENT)
    assert not any("photo.xyz" in n.text for n in result.proposed_nodes if isinstance(n, Question))


def test_the_pair_limit_is_reported_not_silent(corpus: Path) -> None:
    provider = FakeProvider(
        [*_corpus.extraction_script(), PairJudgement(verdict=PairVerdict.CONSISTENT)], usage=USAGE
    )
    agent = EvidenceLedger(owner="ved", max_pairs=1)
    result = agent.run(state(), context(corpus, provider))
    assert not any(
        "pair limit" in s for s in result.self_assessment.least_sure_about
    )  # one pair only
    _ = datetime(2026, 1, 1, tzinfo=UTC)
