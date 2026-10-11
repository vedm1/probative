"""The Actions event, parsed (PB35). `GITHUB_EVENT_PATH` is JSON the runner wrote."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

SUPPORTED_EVENTS = ("pull_request", "pull_request_target")


class ContextError(Exception):
    """The event is not one this action can act on."""


class PullRequestContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo: str
    number: int
    head_repo: str
    head_sha: str
    event_name: str
    action: str
    author_login: str
    author_association: str
    sender_login: str
    labels: tuple[str, ...] = ()
    # the label this event applied (`labeled` only); the PR's `labels` say what it carries now
    event_label: str = ""

    @property
    def is_fork(self) -> bool:
        return self.head_repo != self.repo


def _dig(data: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            raise ContextError(f"the event has no {'.'.join(keys)}")
        data = data[key]
    return data


def load_context(event_path: Path, event_name: str) -> PullRequestContext:
    if event_name not in SUPPORTED_EVENTS:
        raise ContextError(
            f"event {event_name!r} is not supported: use pull_request (or pull_request_target)"
        )
    try:
        event = json.loads(event_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ContextError(f"cannot read the event file {event_path}: {error}") from error
    if not isinstance(event, dict) or "pull_request" not in event:
        raise ContextError("the event is not a pull request event")
    pr = event["pull_request"]
    try:
        head_repo = _dig(pr, "head", "repo", "full_name")
    except ContextError:  # a deleted fork has no head repo
        head_repo = ""
    label = event.get("label") or {}
    if not isinstance(label, dict) or not all(
        isinstance(item, dict) for item in pr.get("labels", [])
    ):
        raise ContextError("the event has a malformed label")
    return PullRequestContext(
        repo=str(_dig(event, "repository", "full_name")),
        number=int(_dig(pr, "number")),
        head_repo=str(head_repo),
        head_sha=str(_dig(pr, "head", "sha")),
        event_name=event_name,
        action=str(event.get("action", "")),
        author_login=str(_dig(pr, "user", "login")),
        author_association=str(pr.get("author_association", "NONE")),
        sender_login=str(_dig(event, "sender", "login")),
        event_label=str(label.get("name", "")),
        labels=tuple(str(label.get("name", "")) for label in pr.get("labels", [])),
    )
