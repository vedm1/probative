"""PB35-p1: `probative github-review` reads the Actions environment and never spends a
model call on a run it will not do."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import probative.cli as cli
from probative.config import MissingCredentialsError
from probative.interfaces.github.entry import run_from_env
from probative.interfaces.github.runner import ActionOptions
from tests.critique._sample import DOC
from tests.critique._scripted import Scripted
from tests.github.conftest import EVENTS, FakeGitHub, target_event


def _env(
    github: FakeGitHub, event: str = "pull_request_same_repo.json", **extra: str
) -> dict[str, str]:
    return {
        "GITHUB_EVENT_PATH": str(EVENTS / event),
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_TOKEN": "ghs_tok",
        "GITHUB_API_URL": github.url,
        **extra,
    }


def _factory_that_must_not_run(model: str) -> object:
    raise AssertionError("a provider was built for a run that does not happen")


def test_a_fork_never_builds_a_provider(github: FakeGitHub) -> None:
    lines: list[str] = []
    code = run_from_env(
        _env(github, "pull_request_fork.json"),
        ActionOptions(),
        provider_factory=_factory_that_must_not_run,  # type: ignore[arg-type]
        echo=lines.append,
    )
    assert code == 0 and github.requests == []
    assert any("fork" in line for line in lines)


def test_a_missing_key_is_a_warning_not_a_crash(github: FakeGitHub) -> None:
    github.add_file("specs/a.md", DOC)

    def no_key(model: str) -> object:
        raise MissingCredentialsError("anthropic")

    lines: list[str] = []
    ok = run_from_env(_env(github), ActionOptions(), provider_factory=no_key, echo=lines.append)  # type: ignore[arg-type]
    strict = run_from_env(
        _env(github),
        ActionOptions(fail_on="block"),
        provider_factory=no_key,
        echo=lines.append,  # type: ignore[arg-type]
    )
    assert (ok, strict) == (0, 2)
    assert any(line.startswith("::warning::") for line in lines)
    assert github.writes() == []


def test_a_missing_token_or_event_is_a_warning(github: FakeGitHub) -> None:
    lines: list[str] = []
    env = _env(github)
    del env["GITHUB_TOKEN"]
    assert (
        run_from_env(env, ActionOptions(), provider_factory=lambda m: Scripted(), echo=lines.append)
        == 0
    )
    assert any("GITHUB_TOKEN" in line for line in lines)


def test_the_api_url_defaults_to_github_dot_com() -> None:
    from probative.interfaces.github.entry import api_url

    assert api_url({}) == "https://api.github.com"
    assert api_url({"GITHUB_API_URL": "https://ghe.example/api/v3"}) == "https://ghe.example/api/v3"


def test_the_cli_command_runs_against_the_fake(github: FakeGitHub, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    github.add_file("specs/a.md", DOC)
    for key, value in _env(github).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cli, "_make_provider", lambda model: Scripted())
    result = CliRunner().invoke(
        cli.app, ["github-review", "--max-files", "3", "--fail-on", "never"]
    )
    assert result.exit_code == 0, result.output
    assert len(github.issue_comments) == 1


def test_the_cli_rejects_a_bad_fail_on(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = CliRunner().invoke(cli.app, ["github-review", "--fail-on", "maybe"])
    assert result.exit_code == 2


# --- PB35-p2: the pull_request_target gate, end to end through the entry point ---------------


def _target_env(github: FakeGitHub, tmp_path: Path, **event: str | None) -> dict[str, str]:
    path = target_event(tmp_path, **event)  # type: ignore[arg-type]
    env = _env(github)
    env["GITHUB_EVENT_PATH"] = str(path)
    env["GITHUB_EVENT_NAME"] = "pull_request_target"
    return env


def _run(env: dict[str, str], lines: list[str], **opts: object) -> int:
    return run_from_env(
        env,
        ActionOptions(**opts),  # type: ignore[arg-type]
        provider_factory=_factory_that_must_not_run,  # type: ignore[arg-type]
        echo=lines.append,
    )


def test_an_outsider_without_the_label_event_costs_nothing_and_asks_nothing(
    github: FakeGitHub, tmp_path: Path
) -> None:
    lines: list[str] = []
    env = _target_env(github, tmp_path, action="opened", label=None)
    assert _run(env, lines) == 0
    assert github.requests == []
    assert any(line.startswith("::notice::") and "probative-review" in line for line in lines)


def test_a_label_from_someone_without_write_builds_no_provider_and_posts_nothing(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.permissions["maintainer"] = "read"
    lines: list[str] = []
    assert _run(_target_env(github, tmp_path), lines) == 0
    assert [r.path for r in github.requests] == [
        "/repos/acme/specs/collaborators/maintainer/permission"
    ]


def test_a_permission_outage_is_a_refusal_not_a_run(github: FakeGitHub, tmp_path: Path) -> None:
    github.permission_status = 500
    lines: list[str] = []
    assert _run(_target_env(github, tmp_path), lines) == 0
    assert github.writes() == []
    assert any("::notice::" in line for line in lines)


def test_the_label_option_changes_which_label_counts(github: FakeGitHub, tmp_path: Path) -> None:
    github.permissions["maintainer"] = "admin"
    lines: list[str] = []
    env = _target_env(github, tmp_path, label="safe-to-review")
    assert _run(env, lines) == 0  # default label does not match
    assert github.requests == []
    github.add_file("specs/a.md", DOC)
    github.head_repo = "mallory/specs"
    code = run_from_env(
        env,
        ActionOptions(label="safe-to-review"),
        provider_factory=lambda m: Scripted(),
        echo=lines.append,
    )
    assert code == 0 and len(github.issue_comments) == 1


def test_an_approved_outsider_runs_with_the_text_only_restriction(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.permissions["maintainer"] = "write"
    github.head_repo = "mallory/specs"
    github.add_file("specs/a.md", DOC)
    github.add_file("specs/b.pdf", b"%PDF", patch=None)
    code = run_from_env(
        _target_env(github, tmp_path),
        ActionOptions(),
        provider_factory=lambda m: Scripted(),
        echo=lambda line: None,
    )
    assert code == 0
    fetched = {r.path.rsplit("/", 1)[-1] for r in github.requests if "/contents/" in r.path}
    assert fetched == {"a.md"}


def test_the_token_never_appears_in_a_refusal(github: FakeGitHub, tmp_path: Path) -> None:
    github.permission_status = 403
    lines: list[str] = []
    env = _target_env(github, tmp_path)
    env["GITHUB_TOKEN"] = "ghs_do_not_print"
    _run(env, lines)
    assert not any("ghs_do_not_print" in line for line in lines)


def test_the_cli_takes_a_label(github: FakeGitHub, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    github.permissions["maintainer"] = "write"
    github.head_repo = "mallory/specs"
    github.add_file("specs/a.md", DOC)
    for key, value in _target_env(github, tmp_path, label="safe-to-review").items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cli, "_make_provider", lambda model: Scripted())
    result = CliRunner().invoke(cli.app, ["github-review", "--label", "safe-to-review"])
    assert result.exit_code == 0, result.output
    assert len(github.issue_comments) == 1


def test_a_refusal_is_green_even_under_fail_on_block(github: FakeGitHub, tmp_path: Path) -> None:
    # documented: a refusal means "not reviewed", so the check is no gate for outsiders
    lines: list[str] = []
    env = _target_env(github, tmp_path, action="opened", label=None)
    assert _run(env, lines, fail_on="block") == 0
