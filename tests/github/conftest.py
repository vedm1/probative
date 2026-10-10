"""A fake GitHub REST API on a local thread (PB35). No network, no token, no key.

It serves what the action reads (the PR's files, file contents at a sha, existing
review and issue comments) and records everything the action writes, so tests
assert on requests rather than on mocks of the client.
"""

from __future__ import annotations

import difflib
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "github"
EVENTS = FIXTURES / "events"
REPO = "acme/specs"
HEAD_SHA = "1" * 40
BOT = {"login": "github-actions[bot]"}


def make_patch(old: str, new: str) -> str:
    """The `patch` field GitHub returns: unified-diff hunks without the file header."""
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=3))
    return "\n".join(diff[2:])


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: Any


@dataclass
class FakeGitHub:
    url: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)
    contents: dict[tuple[str, str], bytes] = field(default_factory=dict)  # (path, ref) -> bytes
    review_comments: list[dict[str, Any]] = field(default_factory=list)
    issue_comments: list[dict[str, Any]] = field(default_factory=list)
    permissions: dict[str, str] = field(default_factory=dict)
    reject_review_with_422: bool = False
    echo_auth_in_errors: bool = False
    fail_files_with: int = 0
    error_message: str = ""
    reject_review_with: int = 0
    requests: list[Request] = field(default_factory=list)
    _next_id: int = 1000

    def add_file(
        self,
        path: str,
        text: str | bytes,
        *,
        old: str = "",
        status: str = "added",
        patch: str | None = "",
        ref: str = HEAD_SHA,
    ) -> None:
        raw = text.encode() if isinstance(text, str) else text
        if patch == "" and isinstance(text, str):
            patch = make_patch(old, text)
        entry: dict[str, Any] = {"filename": path, "status": status}
        if patch is not None:
            entry["patch"] = patch
        self.files.append(entry)
        self.contents[(path, ref)] = raw

    def writes(self) -> list[Request]:
        return [r for r in self.requests if r.method != "GET"]

    def reviews(self) -> list[Request]:
        return [r for r in self.requests if r.method == "POST" and r.path.endswith("/reviews")]

    def reset_log(self) -> None:
        self.requests.clear()

    def new_id(self) -> int:
        self._next_id += 1
        return self._next_id


def _handler(state: FakeGitHub) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # silence
            pass

        def _send(self, status: int, payload: Any, raw: bytes | None = None) -> None:
            body = raw if raw is not None else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Type", "application/json" if raw is None else "text/plain")
            self.end_headers()
            self.wfile.write(body)

        def _record(self) -> tuple[str, dict[str, list[str]], Any]:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            state.requests.append(
                Request(
                    self.command,
                    parsed.path,
                    parse_qs(parsed.query),
                    {k.lower(): v for k, v in self.headers.items()},
                    body,
                )
            )
            return parsed.path, parse_qs(parsed.query), body

        def do_GET(self) -> None:
            path, query, _ = self._record()
            base = f"/repos/{REPO}"
            if path == f"{base}/pulls/7/files":
                if state.fail_files_with:
                    echoed = self.headers.get("Authorization", "")
                    message = state.error_message or echoed
                    return self._send(state.fail_files_with, {"message": message})
                page = int(query.get("page", ["1"])[0])
                size = int(query.get("per_page", ["30"])[0])
                return self._send(200, state.files[(page - 1) * size : page * size])
            if path.startswith(f"{base}/contents/"):
                name = unquote(path[len(f"{base}/contents/") :])
                key = (name, query.get("ref", [""])[0])
                if key not in state.contents:
                    return self._send(404, {"message": "Not Found"})
                return self._send(200, None, raw=state.contents[key])
            if path == f"{base}/pulls/7/comments":
                return self._send(200, state.review_comments)
            if path == f"{base}/issues/7/comments":
                return self._send(200, state.issue_comments)
            if path.startswith(f"{base}/collaborators/") and path.endswith("/permission"):
                who = path.split("/")[-2]
                return self._send(200, {"permission": state.permissions.get(who, "read")})
            if state.echo_auth_in_errors:
                return self._send(500, {"message": self.headers.get("Authorization", "")})
            self._send(404, {"message": f"unhandled GET {path}"})

        def do_POST(self) -> None:
            path, _, body = self._record()
            base = f"/repos/{REPO}"
            if path == f"{base}/pulls/7/reviews":
                if state.reject_review_with and body.get("comments"):
                    return self._send(state.reject_review_with, {"message": "nope"})
                if state.reject_review_with_422 and body.get("comments"):
                    return self._send(422, {"message": "Unprocessable Entity"})
                for c in body.get("comments", []):
                    state.review_comments.append({"id": state.new_id(), "user": BOT, **c})
                return self._send(200, {"id": state.new_id(), "state": "COMMENTED"})
            if path == f"{base}/issues/7/comments":
                made = {"id": state.new_id(), "user": BOT, "body": body["body"]}
                state.issue_comments.append(made)
                return self._send(201, made)
            self._send(404, {"message": f"unhandled POST {path}"})

        def do_PATCH(self) -> None:
            path, _, body = self._record()
            prefix = f"/repos/{REPO}/issues/comments/"
            if path.startswith(prefix):
                wanted = int(path[len(prefix) :])
                for comment in state.issue_comments:
                    if comment["id"] == wanted:
                        comment["body"] = body["body"]
                        return self._send(200, comment)
            self._send(404, {"message": f"unhandled PATCH {path}"})

    return Handler


@pytest.fixture
def github() -> Iterator[FakeGitHub]:
    state = FakeGitHub()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    state.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
