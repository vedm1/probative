from __future__ import annotations

from itertools import product

import pytest
from pydantic import ValidationError

from probative.core.graph.edges import ENDPOINT_RULES, Edge, EdgeType, check_endpoints
from probative.core.graph.nodes import NODE_CLASSES
from tests.core.graph._samples import ENV, all_samples

DESIGN_6_2 = {
    "EVIDENCED_BY", "DERIVED_FROM", "LADDERS_UP_TO", "REQUIRES", "ADDRESSES", "CONTAINS",
    "REALISES", "MEASURED_BY", "CLASSIFIED_AS", "SERVED_BY", "CONTRADICTS", "TESTED_BY",
    "DECIDED_BY", "FLAGGED_BY", "SUPERSEDES", "CURRENT_STATE", "FUTURE_STATE", "PAIN_AT",
    "SATISFIED_BY", "CONSTRAINED_BY", "EVIDENCES_NEED", "DEPENDS_ON", "BASELINED_AS",
    "VARIES_FROM", "IMPLEMENTS", "OBSERVED_AS", "CLAIMED_BY", "CONFLICTS_WITH",
}  # fmt: skip


def test_all_28_design_edge_types_exist_and_have_rules() -> None:
    assert {e.name for e in EdgeType} == DESIGN_6_2
    assert set(ENDPOINT_RULES) == set(EdgeType)


def test_rules_only_name_real_node_types() -> None:
    for srcs, dsts in ENDPOINT_RULES.values():
        for names in (srcs, dsts):
            assert names is None or names <= set(NODE_CLASSES)


def _edge(kind: EdgeType, src: str, dst: str, **attrs: str) -> Edge:
    return Edge.make(type=kind, src=src, dst=dst, attrs=attrs, **ENV)


def test_edge_id_is_derived_from_type_and_endpoints() -> None:
    a = _edge(EdgeType.REQUIRES, "need_aaaaaaaaaaaa", "need_bbbbbbbbbbbb")
    b = _edge(EdgeType.REQUIRES, "need_aaaaaaaaaaaa", "need_bbbbbbbbbbbb")
    assert a.id == b.id and a.id.startswith("edge_")
    assert _edge(EdgeType.REQUIRES, "need_bbbbbbbbbbbb", "need_aaaaaaaaaaaa").id != a.id


def test_endpoint_types_are_enforced() -> None:
    s = all_samples()
    ok = _edge(EdgeType.EVIDENCED_BY, s["claim"].id, s["evidence_span"].id)
    check_endpoints(ok, s["claim"], s["evidence_span"])
    with pytest.raises(ValueError, match="EVIDENCED_BY"):
        check_endpoints(ok, s["need"], s["evidence_span"])
    with pytest.raises(ValueError, match="EVIDENCED_BY"):
        check_endpoints(ok, s["claim"], s["claim"])


def test_tested_by_goes_from_hypothesis_to_test_only() -> None:
    s = all_samples()
    e = _edge(EdgeType.TESTED_BY, s["hypothesis"].id, s["test"].id)
    check_endpoints(e, s["hypothesis"], s["test"])
    with pytest.raises(ValueError):
        check_endpoints(e, s["claim"], s["test"])


@pytest.mark.parametrize("kind", list(EdgeType))
def test_i3_no_edge_of_any_type_runs_from_need_to_feature_idea(kind: EdgeType) -> None:
    s = all_samples()
    e = _edge(kind, s["need"].id, s["feature_idea"].id, reason="r")
    with pytest.raises(ValueError, match="I3"):
        check_endpoints(e, s["need"], s["feature_idea"])


def test_i3_addresses_runs_feature_idea_to_need() -> None:
    s = all_samples()
    check_endpoints(
        _edge(EdgeType.ADDRESSES, s["feature_idea"].id, s["need"].id),
        s["feature_idea"],
        s["need"],
    )
    with pytest.raises(ValueError):
        check_endpoints(
            _edge(EdgeType.ADDRESSES, s["need"].id, s["feature_idea"].id),
            s["need"],
            s["feature_idea"],
        )


def test_every_rule_accepts_a_pair_the_rule_names_and_rejects_one_it_does_not() -> None:
    s = all_samples()
    for kind, (srcs, dsts) in ENDPOINT_RULES.items():
        src_names = sorted(srcs) if srcs else ["claim"]
        dst_names = sorted(dsts) if dsts else ["claim"]
        for sn, dn in product(src_names[:1], dst_names[:1]):
            if sn == "need" and dn == "feature_idea":
                continue
            e = _edge(kind, s[sn].id, s[dn].id, reason="r")
            check_endpoints(e, s[sn], s[dn])
        if srcs is not None:
            outsider = next(n for n in sorted(NODE_CLASSES) if n not in srcs)
            e = _edge(kind, s[outsider].id, s[dst_names[0]].id, reason="r")
            with pytest.raises(ValueError):
                check_endpoints(e, s[outsider], s[dst_names[0]])


def test_supersedes_requires_a_reason_and_the_same_type() -> None:
    with pytest.raises(ValidationError, match="reason"):
        _edge(EdgeType.SUPERSEDES, "claim_aaaaaaaaaaaa", "claim_bbbbbbbbbbbb")
    with pytest.raises(ValidationError, match="reason"):
        _edge(EdgeType.SUPERSEDES, "claim_aaaaaaaaaaaa", "claim_bbbbbbbbbbbb", reason="  ")
    s = all_samples()
    e = _edge(EdgeType.SUPERSEDES, s["claim"].id, s["need"].id, reason="r")
    with pytest.raises(ValueError, match="SUPERSEDES"):
        check_endpoints(e, s["claim"], s["need"])


def test_attrs_are_strings_only_so_no_bare_numbers() -> None:
    with pytest.raises(ValidationError):
        Edge.make(
            type=EdgeType.REQUIRES,
            src="a_aaaaaaaaaaaa",
            dst="b_bbbbbbbbbbbb",
            attrs={"w": 1},
            **ENV,
        )  # type: ignore[dict-item]
