"""PB35-p1: `probative github-review` reads the Actions environment and never spends a
model call on a run it will not do."""

from __future__ import annotations

from typer.testing import CliRunner

import probative.cli as cli
from probative.config import MissingCredentialsError
from probative.interfaces.github.entry import run_from_env
from probative.interfaces.github.runner import ActionOptions
from tests.critique._sample import DOC
from tests.critique._scripted import Scripted
from tests.github.conftest import EVENTS, FakeGitHub


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
