"""What a person may answer at a gate (I6): accept, reject, or amend.

There is no free-text field. A rejection carries a reason from a closed set; an
amendment drops items the patch proposed. A person never types.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from probative.agents.contract import AgentResult
from probative.core.graph.values import Ref
from probative.graph_runtime.patch import Patch


class GateRejectReason(StrEnum):
    WRONG_SCOPE = "wrong_scope"
    NOT_SUPPORTED = "not_supported"
    DUPLICATE = "duplicate"
    OTHER = "other"


class GateDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["accept", "reject", "amend"]
    reason: GateRejectReason | None = None
    drop_ids: tuple[Ref, ...] = ()

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.kind == "accept" and (self.reason or self.drop_ids):
            raise ValueError("accept takes no reason and no ids")
        if self.kind == "reject" and (self.reason is None or self.drop_ids):
            raise ValueError("reject takes a reason and no ids")
        if self.kind == "amend" and (self.reason or not self.drop_ids):
            raise ValueError("amend takes ids to drop and no reason")
        return self


def apply_amend(patch: Patch, drop_ids: tuple[str, ...]) -> Patch:
    """The patch without the named nodes and every edge that touches them.

    The result is a new patch (new id, same cycle). It re-enters the gauntlet;
    an amendment that leaves an orphan claim fails I1 like any other patch.
    """
    present = {n.id for n in patch.result.proposed_nodes}
    unknown = [i for i in drop_ids if i not in present]
    if unknown:
        raise ValueError(f"{unknown[0]} is not in the patch")
    drop = set(drop_ids)
    nodes = tuple(n for n in patch.result.proposed_nodes if n.id not in drop)
    if not nodes:
        raise ValueError("amending would leave the patch empty; reject it instead")
    edges = tuple(e for e in patch.result.proposed_edges if e.src not in drop and e.dst not in drop)
    result = AgentResult(
        proposed_nodes=nodes,
        proposed_edges=edges,
        tool_calls=patch.result.tool_calls,
        rationale=patch.result.rationale,
        self_assessment=patch.result.self_assessment,
        cost=patch.result.cost,
    )
    return Patch.build(patch.agent, patch.phase, patch.cycle, result)
