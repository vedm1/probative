"""A small GitHub REST client on the standard library (PB35).

Stdlib `urllib` keeps the install light and keeps the surface to the half-dozen calls the
action makes. The base URL comes from `GITHUB_API_URL`, so GitHub Enterprise Server works
and tests can point it at a local fake. An error carries the status and GitHub's own
message with the token redacted, never a request header.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, ConfigDict

PAGE_SIZE = 100
MAX_PAGES = 30  # GitHub lists at most 3000 files per pull request
TIMEOUT_SECONDS = 30.0
_JSON = "application/vnd.github+json"
_RAW = "application/vnd.github.raw+json"


class GitHubError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"GitHub API error (HTTP {status}): {message}")


class ChangedFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    status: str
    patch: str | None = None
    previous_path: str | None = None


class GitHubClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def _request(
        self, method: str, path: str, *, body: Any = None, accept: str = _JSON
    ) -> tuple[bytes, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self._base}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": accept,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "probative-github-review",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read(), response.status
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            try:
                message = str(json.loads(detail).get("message", ""))
            except (ValueError, AttributeError):
                message = ""
            raise GitHubError(error.code, self._redact(message)[:300]) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise GitHubError(0, self._redact(str(reason))[:300]) from None

    def _json(self, method: str, path: str, *, body: Any = None) -> Any:
        raw, _ = self._request(method, path, body=body)
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            raise GitHubError(200, "the response was not JSON") from None

    def _paged(self, path: str) -> list[Any]:
        items: list[Any] = []
        joiner = "&" if "?" in path else "?"
        for page in range(1, MAX_PAGES + 1):
            chunk = self._json("GET", f"{path}{joiner}per_page={PAGE_SIZE}&page={page}")
            items.extend(chunk)
            if len(chunk) < PAGE_SIZE:
                break
        return items

    def list_pr_files(self, repo: str, number: int) -> list[ChangedFile]:
        try:
            return [
                ChangedFile(
                    path=item["filename"],
                    status=item["status"],
                    patch=item.get("patch"),
                    previous_path=item.get("previous_filename"),
                )
                for item in self._paged(f"/repos/{repo}/pulls/{number}/files")
            ]
        except (KeyError, TypeError, AttributeError):
            raise GitHubError(200, "the file listing had an unexpected shape") from None

    def get_file(self, repo: str, path: str, ref: str) -> bytes:
        quoted = urllib.parse.quote(path, safe="/")
        raw, _ = self._request(
            "GET", f"/repos/{repo}/contents/{quoted}?ref={urllib.parse.quote(ref)}", accept=_RAW
        )
        return raw

    def pr_head_sha(self, repo: str, number: int) -> str:
        body = self._json("GET", f"/repos/{repo}/pulls/{number}")
        try:
            return str(body["head"]["sha"])
        except (KeyError, TypeError):
            raise GitHubError(200, "the pull request had an unexpected shape") from None

    def collaborator_permission(self, repo: str, login: str) -> str:
        """`admin`, `write`, `read` or `none`. A bot or a stranger is a 200 with `none`."""
        who = urllib.parse.quote(login, safe="")
        body = self._json("GET", f"/repos/{repo}/collaborators/{who}/permission")
        value = body.get("permission") if isinstance(body, dict) else None
        return value if isinstance(value, str) else ""

    def list_review_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        return list(self._paged(f"/repos/{repo}/pulls/{number}/comments"))

    def list_issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        return list(self._paged(f"/repos/{repo}/issues/{number}/comments"))

    def create_review(
        self, repo: str, number: int, commit_id: str, comments: list[dict[str, Any]]
    ) -> None:
        self._json(
            "POST",
            f"/repos/{repo}/pulls/{number}/reviews",
            body={"commit_id": commit_id, "event": "COMMENT", "comments": comments},
        )

    def create_issue_comment(self, repo: str, number: int, body: str) -> dict[str, Any]:
        made: dict[str, Any] = self._json(
            "POST", f"/repos/{repo}/issues/{number}/comments", body={"body": body}
        )
        return made

    def update_issue_comment(self, repo: str, comment_id: int, body: str) -> None:
        self._json("PATCH", f"/repos/{repo}/issues/comments/{comment_id}", body={"body": body})
