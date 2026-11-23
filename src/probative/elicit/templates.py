"""Load the question templates and topics, and fill a template (PB14, D3).

A filled question is the template's own words plus verbatim slot text. No model
writes any of it. The slot text can still carry a loaded phrase from a source, so
`BiasHunter` judges every filled question before a person sees it.
"""

from __future__ import annotations

import string
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from probative.elicit.types import AskedQuestion, Family, QuestionTemplate, Topic

TEMPLATES_PATH = Path(__file__).parent / "templates.yaml"
TOPICS_PATH = Path(__file__).parent / "topics.yaml"


class TemplateError(ValueError):
    pass


def _load(path: Path, key: str) -> list[Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get(key), list):
        raise TemplateError(f"{path.name} must be a mapping with a `{key}` list")
    items: list[Any] = raw[key]
    return items


@cache
def load_templates() -> Mapping[str, QuestionTemplate]:
    found: dict[str, QuestionTemplate] = {}
    for item in _load(TEMPLATES_PATH, "templates"):
        template = QuestionTemplate.model_validate(item)
        if template.id in found:
            raise TemplateError(f"duplicate template id {template.id}")
        found[template.id] = template
    return found


@cache
def load_topics() -> Mapping[str, Topic]:
    found: dict[str, Topic] = {}
    for item in _load(TOPICS_PATH, "topics"):
        topic = Topic.model_validate(item)
        if topic.id in found:
            raise TemplateError(f"duplicate topic id {topic.id}")
        found[topic.id] = topic
    return found


def slots(text: str) -> frozenset[str]:
    return frozenset(name for _, name, _, _ in string.Formatter().parse(text) if name)


def fill(
    template: QuestionTemplate, *, index: int, subject_ref: str, **values: str
) -> AskedQuestion:
    """The template's text with its slots replaced. A missing or extra slot is an error,
    never a silently half-filled question."""
    want = slots(template.text)
    if set(values) != want:
        raise TemplateError(f"{template.id} needs slots {sorted(want)}, got {sorted(values)}")
    return AskedQuestion(
        index=index,
        template_id=template.id,
        subject_ref=subject_ref,
        text=template.text.format(**values),
        options=template.options,
        evidence_kind=template.evidence_kind,
    )


def topic_question(topic: Topic, *, index: int) -> AskedQuestion:
    """A topic is asked as written, with a free-text answer or `unknown`."""
    from probative.elicit.types import AnswerKind, Option

    return AskedQuestion(
        index=index,
        template_id=f"topic:{topic.id}",
        subject_ref=topic.id,
        text=topic.question,
        options=(
            Option(label="I will say what I know", kind=AnswerKind.OPEN),
            Option(label="I do not know", kind=AnswerKind.UNKNOWN),
        ),
        evidence_kind=topic.evidence_kind,
    )


def families_for(mode: str) -> frozenset[Family]:
    """Onboarding mode may use `reconstruct` only (I9); every other mode, `discover`."""
    return frozenset({Family.RECONSTRUCT}) if mode == "onboarding" else frozenset({Family.DISCOVER})
