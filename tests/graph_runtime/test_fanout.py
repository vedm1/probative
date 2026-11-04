from __future__ import annotations

import random

from probative.core.candidates import CandidateKind, ClaimCandidate, NeedCandidate, candidate_id
from probative.core.critic import Severity
from probative.core.evidence import EvidenceSpan, Locator
from probative.graph_runtime.fanout import run_critic_fanout
from tests.graph_runtime._critics import ScriptedCritic


def need(text: str) -> NeedCandidate:
    span = EvidenceSpan(
        source_id="need_" + "0" * 12, start=0, end=len(text), text=text, locator=Locator()
    )
    return NeedCandidate(id=candidate_id(CandidateKind.NEED, span), evidence=span)


def claim(text: str) -> ClaimCandidate:
    span = EvidenceSpan(
        source_id="claim_" + "0" * 12, start=0, end=len(text), text=text, locator=Locator()
    )
    return ClaimCandidate(id=candidate_id(CandidateKind.CLAIM, span), evidence=span)


def test_findings_come_back_in_critic_order_whatever_finishes_first() -> None:
    n = need("Reduce re-keying")
    for _ in range(5):
        delays = [0.0, 0.03, 0.06, 0.09]
        random.shuffle(delays)
        critics = [
            (f"c{i}", ScriptedCritic(f"c{i}", flag=lambda c: True, delay=d), [n])
            for i, d in enumerate(delays)
        ]
        out = run_critic_fanout(critics)
        assert [f.critic_id for f in out.findings] == ["c0", "c1", "c2", "c3"]


def test_a_critic_only_sees_candidates_its_rubric_applies_to() -> None:
    n, c = need("Reduce re-keying"), claim("Clerks lose time")
    only_needs = ScriptedCritic("only_needs", applies_to=["NeedCandidate"])
    everything = ScriptedCritic("everything")
    run_critic_fanout([("only_needs", only_needs, [n, c]), ("everything", everything, [n, c])])
    assert only_needs.seen == [n.id]
    assert sorted(everything.seen) == sorted([n.id, c.id])


def test_a_critic_with_nothing_to_judge_is_not_called() -> None:
    critic = ScriptedCritic("x", applies_to=["StoryCandidate"])
    run_critic_fanout([("x", critic, [need("Reduce re-keying")])])
    assert critic.calls == 0


def test_a_raising_critic_becomes_a_blocking_finding() -> None:
    n = need("Reduce re-keying")
    ok = ScriptedCritic("ok", flag=lambda c: True, severity=Severity.WARN)
    bad = ScriptedCritic("bad", boom=RuntimeError("model unreachable"))
    out = run_critic_fanout([("ok", ok, [n]), ("bad", bad, [n])])
    errors = [f for f in out.findings if f.check_id == "critic_error"]
    assert len(errors) == 1
    assert errors[0].critic_id == "bad" and errors[0].severity is Severity.BLOCK
    assert "model unreachable" in errors[0].message
    assert any(f.critic_id == "ok" for f in out.findings)


def test_token_usage_is_the_delta_this_run_caused() -> None:
    n = need("Reduce re-keying")
    critic = ScriptedCritic("x", tokens=7)
    first = run_critic_fanout([("x", critic, [n])])
    second = run_critic_fanout([("x", critic, [n])])
    assert first.tokens == 7 and second.tokens == 7


def test_a_critic_without_stats_costs_nothing() -> None:
    critic = ScriptedCritic("x")
    del critic.stats
    assert run_critic_fanout([("x", critic, [need("Reduce re-keying")])]).tokens == 0
