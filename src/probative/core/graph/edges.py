"""Edge types and their endpoint rules (docs/DESIGN.md §6.2).

An edge is `(type, src, dst)` and its id is derived from exactly that. The
rules are data: `ENDPOINT_RULES[type] = (allowed src types, allowed dst types)`
with `None` meaning any node type.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationInfo,
    model_validator,
)

from probative.core.graph._ids import ID_REGEX, derive_id
from probative.core.graph.nodes import NodeBase
from probative.core.graph.values import UtcDatetime


class EdgeType(StrEnum):
    EVIDENCED_BY = "EVIDENCED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    LADDERS_UP_TO = "LADDERS_UP_TO"
    REQUIRES = "REQUIRES"
    ADDRESSES = "ADDRESSES"
    CONTAINS = "CONTAINS"
    REALISES = "REALISES"
    MEASURED_BY = "MEASURED_BY"
    CLASSIFIED_AS = "CLASSIFIED_AS"
    SERVED_BY = "SERVED_BY"
    CONTRADICTS = "CONTRADICTS"
    TESTED_BY = "TESTED_BY"
    DECIDED_BY = "DECIDED_BY"
    FLAGGED_BY = "FLAGGED_BY"
    SUPERSEDES = "SUPERSEDES"
    CURRENT_STATE = "CURRENT_STATE"
    FUTURE_STATE = "FUTURE_STATE"
    PAIN_AT = "PAIN_AT"
    SATISFIED_BY = "SATISFIED_BY"
    CONSTRAINED_BY = "CONSTRAINED_BY"
    EVIDENCES_NEED = "EVIDENCES_NEED"
    DEPENDS_ON = "DEPENDS_ON"
    BASELINED_AS = "BASELINED_AS"
    VARIES_FROM = "VARIES_FROM"
    IMPLEMENTS = "IMPLEMENTS"
    OBSERVED_AS = "OBSERVED_AS"
    CLAIMED_BY = "CLAIMED_BY"
    CONFLICTS_WITH = "CONFLICTS_WITH"


_Types = frozenset[str] | None


def _t(*names: str) -> frozenset[str]:
    return frozenset(names)


ENDPOINT_RULES: dict[EdgeType, tuple[_Types, _Types]] = {
    EdgeType.EVIDENCED_BY: (_t("claim"), _t("evidence_span")),
    EdgeType.DERIVED_FROM: (None, None),
    EdgeType.LADDERS_UP_TO: (_t("need"), _t("need")),
    EdgeType.REQUIRES: (_t("need"), _t("need")),
    EdgeType.ADDRESSES: (_t("feature_idea"), _t("need")),
    EdgeType.CONTAINS: (_t("feature_idea"), _t("feature_chunk")),
    EdgeType.REALISES: (_t("story"), _t("feature_chunk")),
    EdgeType.MEASURED_BY: (_t("need"), _t("rating")),
    EdgeType.CLASSIFIED_AS: (_t("need"), _t("kano_class")),
    EdgeType.SERVED_BY: (_t("need"), _t("alternative")),
    EdgeType.CONTRADICTS: (_t("claim"), _t("claim")),
    EdgeType.TESTED_BY: (_t("hypothesis"), _t("test")),
    EdgeType.DECIDED_BY: (None, _t("decision")),
    EdgeType.FLAGGED_BY: (None, _t("finding")),
    EdgeType.SUPERSEDES: (None, None),  # same type on both ends, checked separately
    EdgeType.CURRENT_STATE: (_t("process_model"), _t("incumbent_system")),
    EdgeType.FUTURE_STATE: (_t("process_model"), _t("value_prop")),
    EdgeType.PAIN_AT: (_t("need"), _t("process_step")),
    EdgeType.SATISFIED_BY: (_t("need"), _t("incumbent_system")),
    EdgeType.CONSTRAINED_BY: (_t("story", "need"), _t("constraint")),
    EdgeType.EVIDENCES_NEED: (_t("workaround"), _t("need")),
    EdgeType.DEPENDS_ON: (_t("story", "feature_chunk"), _t("dependency")),
    EdgeType.BASELINED_AS: (None, _t("baseline")),
    EdgeType.VARIES_FROM: (None, _t("baseline")),
    EdgeType.IMPLEMENTS: (_t("build_phase"), _t("story")),
    EdgeType.OBSERVED_AS: (_t("story"), _t("delivery_signal")),
    EdgeType.CLAIMED_BY: (None, _t("partition")),
    EdgeType.CONFLICTS_WITH: (None, None),
}

_DERIVE = "derive_id"


def _freeze(m: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(m))


def _no_attrs() -> Mapping[str, str]:
    return MappingProxyType({})


_Attrs = Annotated[
    Mapping[str, str],
    AfterValidator(_freeze),
    PlainSerializer(lambda m: dict(m), return_type=dict[str, str]),
]


class Edge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=ID_REGEX)
    type: EdgeType
    src: str = Field(pattern=ID_REGEX)
    dst: str = Field(pattern=ID_REGEX)
    partition: str = Field(default="main", min_length=1)
    owner: str = Field(min_length=1)
    asserted_at: UtcDatetime
    attrs: _Attrs = Field(default_factory=_no_attrs)  # strings only: no bare numbers, immutable

    @classmethod
    def make(cls, **fields: Any) -> Self:
        return cls.model_validate({"id": "edge_000000000000", **fields}, context={_DERIVE: True})

    @model_validator(mode="after")
    def _derived_id_and_reason(self, info: ValidationInfo) -> Self:
        if self.type is EdgeType.SUPERSEDES and not self.attrs.get("reason", "").strip():
            raise ValueError("a SUPERSEDES edge needs a non-empty attrs['reason'] (I7)")
        want = derive_id("edge", self.partition, [self.type.value, self.src, self.dst])
        if info.context and info.context.get(_DERIVE):
            object.__setattr__(self, "id", want)
        elif self.id != want:
            raise ValueError(f"id {self.id!r} is not the derived id for this edge ({want!r})")
        return self


def check_endpoints(edge: Edge, src: NodeBase, dst: NodeBase) -> None:
    """Raise `ValueError` if the edge may not join these two nodes."""
    s, d = src.type_name(), dst.type_name()
    name = edge.type.name
    if s == "need" and d == "feature_idea":
        raise ValueError(
            f"I3: {name} from a need to a feature idea; a Need may never reference a FeatureIdea"
        )
    allowed_src, allowed_dst = ENDPOINT_RULES[edge.type]
    if (allowed_src is not None and s not in allowed_src) or (
        allowed_dst is not None and d not in allowed_dst
    ):
        raise ValueError(f"{name} may not join {s} to {d}")
    if edge.type is EdgeType.SUPERSEDES and s != d:
        raise ValueError(f"SUPERSEDES must join two nodes of one type, not {s} to {d}")
