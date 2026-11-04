from __future__ import annotations

from pathlib import Path

import pytest

from probative.core.critic import Severity
from probative.graph_runtime.budget import BudgetLedger
from probative.graph_runtime.phases import PHASES, Phase
from probative.graph_runtime.tedium import Interaction, InteractionLog, TediumAuditor


def test_ledger_charges_and_reports_remaining() -> None:
    ledger = BudgetLedger(token_budget=100, wall_seconds=10.0)
    ledger.charge(tokens=30, seconds=2.5)
    view = ledger.view()
    assert (view.tokens_left, view.seconds_left) == (70, 7.5)
    assert not view.exhausted


def test_ledger_is_exhausted_by_either_limit() -> None:
    a = BudgetLedger(token_budget=10, wall_seconds=100.0)
    a.charge(tokens=10, seconds=0.0)
    assert a.view().exhausted
    b = BudgetLedger(token_budget=10, wall_seconds=1.0)
    b.charge(tokens=0, seconds=1.0)
    assert b.view().exhausted


def test_overspend_does_not_go_negative_in_the_view() -> None:
    ledger = BudgetLedger(token_budget=10, wall_seconds=1.0)
    ledger.charge(tokens=99, seconds=9.0)
    assert ledger.view().tokens_left == 0 and ledger.view().seconds_left == 0.0


def test_negative_charge_is_refused() -> None:
    with pytest.raises(ValueError):
        BudgetLedger(token_budget=10, wall_seconds=1.0).charge(tokens=-1, seconds=0.0)


def test_log_appends_and_reads_back(tmp_path: Path) -> None:
    log = InteractionLog(tmp_path / "i.jsonl")
    log.record(Interaction(phase=Phase.P2, kind="gate", seconds=12.5))
    log.record(Interaction(phase=Phase.P2, kind="escalation", seconds=3.0))
    again = InteractionLog(tmp_path / "i.jsonl").entries()
    assert [(i.phase, i.kind) for i in again] == [(Phase.P2, "gate"), (Phase.P2, "escalation")]


def test_auditor_is_quiet_within_budget() -> None:
    entries = [Interaction(phase=Phase.P2, kind="gate", seconds=5.0)]
    findings = TediumAuditor().audit(entries, PHASES)
    assert {f.severity for f in findings} == {Severity.NOTE}


def test_auditor_warns_on_a_phase_over_its_interaction_budget() -> None:
    n = PHASES[Phase.P2].interaction_budget + 1
    entries = [Interaction(phase=Phase.P2, kind="gate", seconds=1.0)] * n
    warns = [f for f in TediumAuditor().audit(entries, PHASES) if f.severity is Severity.WARN]
    assert any(f.check_id == "phase_over_budget" and "P2" in f.message for f in warns)


def test_auditor_warns_when_a_run_has_more_than_five_gates() -> None:
    entries = [Interaction(phase=Phase.P3, kind="gate", seconds=1.0)] * 6
    warns = [f for f in TediumAuditor().audit(entries, PHASES) if f.severity is Severity.WARN]
    assert any(f.check_id == "run_gates_over_budget" for f in warns)


def test_auditor_warns_when_a_run_has_more_than_forty_interactions() -> None:
    entries = [Interaction(phase=Phase.P3, kind="escalation", seconds=1.0)] * 41
    warns = [f for f in TediumAuditor().audit(entries, PHASES) if f.severity is Severity.WARN]
    assert any(f.check_id == "run_over_budget" for f in warns)
