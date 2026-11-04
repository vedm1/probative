from __future__ import annotations

import pytest
from pydantic import ValidationError

from probative.agents.contract import AgentResult, CostRecord, SelfAssessment, TierPolicy
from probative.core.evidence import Tier
from tests.graph_runtime._support import good_ratings, result


def test_agent_result_is_frozen_and_typed() -> None:
    r = result(list(good_ratings()))
    assert len(r.proposed_nodes) == 2
    with pytest.raises(ValidationError):
        r.rationale = "changed"  # type: ignore[misc]


def test_cost_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        CostRecord(input_tokens=-1, output_tokens=0, wall_seconds=0.0)


def test_agent_result_round_trips_through_json() -> None:
    r = result(list(good_ratings()))
    again = AgentResult.model_validate_json(r.model_dump_json())
    assert [n.id for n in again.proposed_nodes] == [n.id for n in r.proposed_nodes]


def test_tier_policy_allows_only_what_it_names() -> None:
    p = TierPolicy(allowed=frozenset({Tier.T1}))
    assert Tier.T1 in p.allowed and Tier.T3 not in p.allowed


def test_self_assessment_defaults_empty() -> None:
    assert SelfAssessment().least_sure_about == ()
