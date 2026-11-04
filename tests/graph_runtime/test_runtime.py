from __future__ import annotations

import json
from pathlib import Path

import pytest

from probative.core.critic import Severity
from probative.core.evidence import Tier
from probative.core.graph import store
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim
from probative.graph_runtime.gates import GateDecision, GateRejectReason
from probative.graph_runtime.modes import MODES, Mode
from probative.graph_runtime.phases import Phase
from probative.graph_runtime.runfiles import RunFiles, read_jsonl
from probative.graph_runtime.runtime import (
    ModeViolationError,
    NoPendingDecisionError,
    RunRefusedError,
)
from tests.core.graph._samples import ENV, conf
from tests.graph_runtime._agents import ScriptedAgent
from tests.graph_runtime._critics import ScriptedCritic
from tests.graph_runtime._harness import (
    agent_by_cycle,
    decide,
    good,
    need,
    orphan_hypothesis,
    phases,
    runtime,
)
from tests.graph_runtime._support import good_ratings, hypothesis_with_test, opportunity, result

ACCEPT = GateDecision(kind="accept")


def files_of(tmp_path: Path) -> RunFiles:
    return RunFiles(tmp_path / "run1")


# -- the straight path --------------------------------------------------------


def test_a_phase_with_no_gate_commits_on_its_own(tmp_path: Path) -> None:
    agent = ScriptedAgent(good)
    rt = runtime(tmp_path, {Phase.P1: agent})
    out = rt.start(Phase.P1)
    assert out.status == "committed" and agent.calls == 1
    graph = store.read_graph(files_of(tmp_path).graph_path)
    assert need().id in graph.nodes
    assert out.graph_hash == store.content_hash(graph)


def test_the_agent_is_shown_the_graph_the_cycle_and_nothing_to_mutate(tmp_path: Path) -> None:
    agent = ScriptedAgent(good)
    runtime(tmp_path, {Phase.P1: agent}).start(Phase.P1)
    (state,) = agent.states
    assert state.cycle == 1 and state.phase is Phase.P1 and state.mode is Mode.SOLO
    assert state.graph.nodes == {} and state.prior_findings == ()
    with pytest.raises(TypeError):
        state.graph.nodes["x"] = None  # type: ignore[index]


def test_a_number_is_computed_by_the_formula_not_the_agent(tmp_path: Path) -> None:
    imp, sat = good_ratings()
    agent = ScriptedAgent(lambda s, c: result([imp, sat, opportunity([imp, sat])]))
    runtime(tmp_path, {Phase.P1: agent}).start(Phase.P1)
    graph = store.read_graph(files_of(tmp_path).graph_path)
    (opp,) = [n for n in graph.nodes.values() if n.type_name() == "opportunity"]
    assert opp.value.value == 15  # type: ignore[attr-defined]


# -- the repair loop ------------------------------------------------------------


def test_a_patch_fixed_on_cycle_two_commits_on_cycle_two(tmp_path: Path) -> None:
    def fix(cycle: int):  # type: ignore[no-untyped-def]
        if cycle == 1:
            return orphan_hypothesis()
        nodes, edges = hypothesis_with_test()
        return nodes, edges

    agent = agent_by_cycle(fix)
    critic = ScriptedCritic("evidence_auditor", applies_to=["NeedCandidate"])
    rt = runtime(
        tmp_path,
        {Phase.P1: agent},
        critics={"evidence_auditor": critic},
        table=phases(critics=frozenset({"evidence_auditor"})),
    )
    out = rt.start(Phase.P1)
    assert out.status == "committed" and agent.calls == 2
    assert [v.code for v in agent.states[1].prior_violations] == ["I2_NO_TEST"]
    rejected = list(files_of(tmp_path).rejected_dir.glob("*.json"))
    assert len(rejected) == 1
    assert json.loads(rejected[0].read_text())["violations"][0]["code"] == "I2_NO_TEST"


def test_critics_do_not_run_on_a_cycle_that_already_failed_a_validator(tmp_path: Path) -> None:
    critic = ScriptedCritic("evidence_auditor")
    agent = agent_by_cycle(lambda cycle: orphan_hypothesis())
    rt = runtime(
        tmp_path,
        {Phase.P1: agent},
        critics={"evidence_auditor": critic},
        table=phases(critics=frozenset({"evidence_auditor"})),
    )
    rt.start(Phase.P1)
    assert critic.calls == 0


def test_a_patch_never_fixed_escalates_after_exactly_three_cycles(tmp_path: Path) -> None:
    agent = agent_by_cycle(lambda cycle: orphan_hypothesis())
    rt = runtime(tmp_path, {Phase.P1: agent})
    out = rt.start(Phase.P1)
    assert out.status == "awaiting_escalation" and agent.calls == 3
    assert not files_of(tmp_path).graph_path.exists()
    assert len(list(files_of(tmp_path).rejected_dir.glob("*.json"))) == 3
    pending = rt.pending(Phase.P1)
    assert pending is not None and pending.kind == "escalation"
    assert {v.code for v in pending.violations} == {"I2_NO_TEST"}


def test_a_blocking_critic_finding_sends_the_patch_back_with_the_finding(tmp_path: Path) -> None:
    def fix(cycle: int):  # type: ignore[no-untyped-def]
        return [
            need("Provide a dashboard" if cycle == 1 else "Reduce the time I spend re-keying")
        ], []

    agent = agent_by_cycle(fix)
    critic = ScriptedCritic("space_warden", flag=lambda c: "dashboard" in c.text)  # type: ignore[attr-defined]
    rt = runtime(
        tmp_path,
        {Phase.P1: agent},
        critics={"space_warden": critic},
        table=phases(critics=frozenset({"space_warden"})),
    )
    out = rt.start(Phase.P1)
    assert out.status == "committed" and agent.calls == 2
    (seen,) = agent.states[1].prior_findings
    assert seen.critic_id == "space_warden" and seen.severity is Severity.BLOCK
    graph = store.read_graph(files_of(tmp_path).graph_path)
    assert all(n.type_name() != "finding" for n in graph.nodes.values())


def test_a_warning_commits_and_becomes_a_finding_node_on_the_flagged_node(tmp_path: Path) -> None:
    critic = ScriptedCritic("evidence_auditor", flag=lambda c: True, severity=Severity.WARN)
    rt = runtime(
        tmp_path,
        {Phase.P1: ScriptedAgent(good)},
        critics={"evidence_auditor": critic},
        table=phases(critics=frozenset({"evidence_auditor"})),
    )
    assert rt.start(Phase.P1).status == "committed"
    graph = store.read_graph(files_of(tmp_path).graph_path)
    (flagged,) = graph.out_edges(need().id)
    assert graph.nodes[flagged.dst].type_name() == "finding"


def test_a_critic_that_raises_blocks_the_patch(tmp_path: Path) -> None:
    critic = ScriptedCritic("evidence_auditor", boom=RuntimeError("down"))
    agent = ScriptedAgent(good)
    rt = runtime(
        tmp_path,
        {Phase.P1: agent},
        critics={"evidence_auditor": critic},
        table=phases(critics=frozenset({"evidence_auditor"})),
    )
    out = rt.start(Phase.P1)
    assert out.status == "awaiting_escalation" and agent.calls == 3


# -- the escalation choices -----------------------------------------------------


def stuck(tmp_path: Path):  # type: ignore[no-untyped-def]
    agent = agent_by_cycle(lambda cycle: orphan_hypothesis())
    rt = runtime(tmp_path, {Phase.P1: agent})
    rt.start(Phase.P1)
    return rt, agent


def test_an_escalation_cannot_be_accepted(tmp_path: Path) -> None:
    rt, _ = stuck(tmp_path)
    with pytest.raises(ValueError, match="cannot be accepted"):
        decide(rt, Phase.P1, ACCEPT)


def test_rejecting_an_escalation_starts_a_fresh_set_of_cycles(tmp_path: Path) -> None:
    rt, agent = stuck(tmp_path)
    out = decide(rt, Phase.P1, GateDecision(kind="reject", reason=GateRejectReason.WRONG_SCOPE))
    assert out.status == "awaiting_escalation" and agent.calls == 6
    assert agent.states[3].reject_reason is GateRejectReason.WRONG_SCOPE
    assert agent.states[3].cycle == 1


def test_amending_an_escalation_drops_the_bad_node_and_commits_the_rest(tmp_path: Path) -> None:
    def fix(cycle: int):  # type: ignore[no-untyped-def]
        bad, _ = orphan_hypothesis()
        return [*bad, need()], []

    rt = runtime(tmp_path, {Phase.P1: agent_by_cycle(fix)})
    rt.start(Phase.P1)
    pending = rt.pending(Phase.P1)
    assert pending is not None
    hypothesis_id = next(
        n.id for n in pending.patch.result.proposed_nodes if n.type_name() == "hypothesis"
    )
    out = decide(rt, Phase.P1, GateDecision(kind="amend", drop_ids=(hypothesis_id,)))
    assert out.status == "committed"
    graph = store.read_graph(files_of(tmp_path).graph_path)
    assert need().id in graph.nodes and hypothesis_id not in graph.nodes


def test_deciding_with_nothing_pending_is_an_error(tmp_path: Path) -> None:
    rt = runtime(tmp_path, {Phase.P1: ScriptedAgent(good)})
    rt.start(Phase.P1)
    with pytest.raises(NoPendingDecisionError):
        rt.decide(Phase.P1, ACCEPT, patch_id="patch_000000000000")


# -- gates and the checkpoint -----------------------------------------------------


def gated(tmp_path: Path, agent: ScriptedAgent | None = None):  # type: ignore[no-untyped-def]
    agent = agent or ScriptedAgent(good)
    rt = runtime(tmp_path, {Phase.P2: agent})
    return rt, agent, rt.start(Phase.P2)


def test_a_gated_phase_pauses_and_commits_nothing(tmp_path: Path) -> None:
    rt, _agent, out = gated(tmp_path)
    assert out.status == "awaiting_gate"
    assert not files_of(tmp_path).graph_path.exists()
    pending = rt.pending(Phase.P2)
    assert pending is not None and pending.kind == "gate" and pending.gate == "G1"


def test_a_gate_resumes_in_a_new_runtime_from_the_checkpoint_file(tmp_path: Path) -> None:
    rt, _agent, _ = gated(tmp_path)
    rt.close()
    again_agent = ScriptedAgent(good)
    again = runtime(tmp_path, {Phase.P2: again_agent})
    assert again.pending(Phase.P2) is not None
    out = decide(again, Phase.P2, ACCEPT)
    assert out.status == "committed" and again_agent.calls == 0
    assert need().id in store.read_graph(files_of(tmp_path).graph_path).nodes


def test_a_rejected_gate_goes_back_to_the_producer_with_the_reason(tmp_path: Path) -> None:
    rt, agent, _ = gated(tmp_path)
    out = decide(rt, Phase.P2, GateDecision(kind="reject", reason=GateRejectReason.NOT_SUPPORTED))
    assert out.status == "awaiting_gate" and agent.calls == 2
    assert agent.states[1].reject_reason is GateRejectReason.NOT_SUPPORTED


def test_an_amended_gate_commits_only_what_remains(tmp_path: Path) -> None:
    keep, drop = need(), need("Know when my approval is overdue")
    agent = ScriptedAgent(lambda s, c: result([keep, drop]))
    rt, _, _ = gated(tmp_path, agent)
    out = decide(rt, Phase.P2, GateDecision(kind="amend", drop_ids=(drop.id,)))
    assert out.status == "awaiting_gate"  # the amended patch is judged again, then asks again
    out = decide(rt, Phase.P2, ACCEPT)
    graph = store.read_graph(files_of(tmp_path).graph_path)
    assert out.status == "committed" and keep.id in graph.nodes and drop.id not in graph.nodes


def test_the_same_run_twice_gives_the_same_graph_and_ledger(tmp_path: Path) -> None:
    hashes, ledgers = [], []
    for sub in ("a", "b"):
        base = tmp_path / sub
        base.mkdir()
        rt = runtime(base, {Phase.P2: ScriptedAgent(good)})
        rt.start(Phase.P2)
        decide(rt, Phase.P2, ACCEPT)
        hashes.append(store.content_hash(store.read_graph(RunFiles(base / "run1").graph_path)))
        ledgers.append(
            [
                {k: v for k, v in line.items() if k != "committed_at"}
                for line in read_jsonl(RunFiles(base / "run1").ledger_path)
            ]
        )
    assert hashes[0] == hashes[1] and ledgers[0] == ledgers[1]


def test_the_two_phase_run_is_clean_under_both_validators(tmp_path: Path) -> None:
    from probative.formulas.validator import FormulaValidator

    imp, sat = good_ratings()
    rt = runtime(
        tmp_path,
        {
            Phase.P1: ScriptedAgent(good),
            Phase.P3: ScriptedAgent(lambda s, c: result([imp, sat, opportunity([imp, sat])])),
        },
    )
    rt.start(Phase.P1)
    rt.start(Phase.P3)
    decide(rt, Phase.P3, ACCEPT)
    graph = store.read_graph(files_of(tmp_path).graph_path)
    assert len(graph.nodes) == 4
    assert rt.committer.verify_clean(graph) == []
    assert FormulaValidator().check(graph) == []


# -- starting from a bad graph ------------------------------------------------------


def test_a_run_refuses_to_start_from_a_graph_with_violations(tmp_path: Path) -> None:
    files = files_of(tmp_path)
    files.ensure()
    dirty = Graph.empty().with_patch(
        nodes=[Claim.make(text="Users wait.", tier=Tier.T3, confidence=conf(), **ENV)]
    )
    store.write_graph(dirty, files.graph_path)
    rt = runtime(tmp_path, {Phase.P1: ScriptedAgent(good)})
    with pytest.raises(RunRefusedError, match="I1_ORPHAN_CLAIM"):
        rt.start(Phase.P1)


def test_a_phase_without_an_agent_is_refused(tmp_path: Path) -> None:
    rt = runtime(tmp_path, {Phase.P1: ScriptedAgent(good)})
    with pytest.raises(RunRefusedError, match="no agent"):
        rt.start(Phase.P4)


# -- budgets -------------------------------------------------------------------------


def test_a_spent_token_budget_skips_critics_loudly_not_silently(tmp_path: Path) -> None:
    critic = ScriptedCritic("evidence_auditor", flag=lambda c: True, severity=Severity.BLOCK)
    agent = ScriptedAgent(lambda s, c: result([need()], tokens=500))
    rt = runtime(
        tmp_path,
        {Phase.P1: agent},
        critics={"evidence_auditor": critic},
        table=phases(tokens=100, critics=frozenset({"evidence_auditor"})),
    )
    out = rt.start(Phase.P1)
    assert out.status == "awaiting_gate" and critic.calls == 0  # a person must see it
    assert decide(rt, Phase.P1, ACCEPT).status == "committed"
    (line,) = read_jsonl(files_of(tmp_path).ledger_path)
    assert [f["check_id"] for f in line["findings"]] == ["critic_skipped_budget"]
    assert line["findings"][0]["severity"] == "warn"


def test_a_spent_budget_stops_the_producer_instead_of_looping(tmp_path: Path) -> None:
    agent = agent_by_cycle(lambda cycle: orphan_hypothesis())
    table = phases(tokens=5, critics=frozenset())
    rt = runtime(tmp_path, {Phase.P1: agent}, table=table)
    out = rt.start(Phase.P1)
    assert out.status == "budget_exhausted" and agent.calls == 1
    assert not files_of(tmp_path).graph_path.exists()


# -- modes ----------------------------------------------------------------------------


def test_onboarding_refuses_a_critic_the_mode_omits(tmp_path: Path) -> None:
    with pytest.raises(ModeViolationError, match="red_team"):
        runtime(
            tmp_path,
            {Phase.P1: ScriptedAgent(good)},
            mode=Mode.ONBOARDING,
            critics={"red_team": ScriptedCritic("red_team")},
        )


def test_onboarding_never_calls_the_evaluative_critics(tmp_path: Path) -> None:
    rt = runtime(
        tmp_path,
        {Phase.P1: ScriptedAgent(good)},
        mode=Mode.ONBOARDING,
        table=phases(),  # the real critic lists, narrowed to nothing by the mode
    )
    assert rt.start(Phase.P1).status == "committed"
    assert MODES[Mode.ONBOARDING].critics == frozenset()


def test_a_critic_the_phase_needs_but_was_not_supplied_is_refused(tmp_path: Path) -> None:
    rt = runtime(
        tmp_path,
        {Phase.P1: ScriptedAgent(good)},
        table=phases(critics=frozenset({"space_warden"})),
    )
    with pytest.raises(RunRefusedError, match="space_warden"):
        rt.start(Phase.P1)


# -- I6 and I7 --------------------------------------------------------------------------


def test_the_tedium_counters_equal_the_interrupts(tmp_path: Path) -> None:
    rt, _, _ = gated(tmp_path)
    decide(rt, Phase.P2, GateDecision(kind="reject", reason=GateRejectReason.DUPLICATE))
    decide(rt, Phase.P2, ACCEPT)
    entries = rt.interactions.entries()
    assert [(e.phase, e.kind) for e in entries] == [(Phase.P2, "gate"), (Phase.P2, "gate")]
    assert all(e.seconds >= 0 for e in entries)
    assert any(f.check_id == "interaction_count" for f in rt.audit_tedium())


def test_the_variance_hook_runs_once_per_commit(tmp_path: Path) -> None:
    class Spy:
        calls = 0

        def on_commit(self, before: Graph, after: Graph, patch: object) -> None:
            Spy.calls += 1

    rt = runtime(tmp_path, {Phase.P1: ScriptedAgent(good)}, variance=Spy())
    rt.start(Phase.P1)
    assert Spy.calls == 1


def test_the_assumption_ledger_keeps_what_the_agent_was_least_sure_about(tmp_path: Path) -> None:
    from probative.agents.contract import SelfAssessment

    def produce(s, c):  # type: ignore[no-untyped-def]
        r = result([need()])
        return r.model_copy(update={"self_assessment": SelfAssessment(least_sure_about=("n=3",))})

    runtime(tmp_path, {Phase.P1: ScriptedAgent(produce)}).start(Phase.P1)
    (line,) = read_jsonl(files_of(tmp_path).assumptions_path)
    assert line["least_sure_about"] == ["n=3"]
