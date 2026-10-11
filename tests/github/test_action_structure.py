"""PB35-p1: `action.yml` and the example workflow are safe by construction."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())
EXAMPLE = yaml.safe_load((ROOT / "docs" / "examples" / "probative-critique.yml").read_text())


def _steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = ACTION["runs"]["steps"]
    return steps


def test_it_is_a_composite_action_with_the_expected_inputs() -> None:
    assert ACTION["runs"]["using"] == "composite"
    assert {
        "anthropic-api-key",
        "github-token",
        "paths",
        "max-files",
        "max-minutes",
        "max-inline",
        "fail-on",
        "model",
        "version",
        "install-from",
    } <= set(ACTION["inputs"])


def test_no_input_or_event_value_is_interpolated_into_a_script() -> None:
    for step in _steps():
        script = step.get("run", "")
        assert "${{" not in script, "pass values through env:, not into the script text"


def test_the_defaults_are_advisory_and_capped() -> None:
    inputs = ACTION["inputs"]
    assert inputs["fail-on"]["default"] == "never"
    assert inputs["max-files"]["default"] == "25"
    assert inputs["github-token"]["default"] == "${{ github.token }}"


def test_the_pinned_version_follows_the_package() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert ACTION["inputs"]["version"]["default"] == project["version"]


def test_the_action_uses_the_same_uv_setup_as_ci() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    used = [s["uses"] for s in _steps() if "uses" in s]
    assert used == ["astral-sh/setup-uv@v7"]
    assert "astral-sh/setup-uv@v7" in ci


def test_the_secret_only_reaches_the_command_through_the_environment() -> None:
    run = next(s for s in _steps() if "run" in s)
    assert run["env"]["ANTHROPIC_API_KEY"] == "${{ inputs.anthropic-api-key }}"
    assert "ANTHROPIC_API_KEY" not in run["run"]


def test_the_example_asks_for_the_least_permission_and_avoids_pull_request_target() -> None:
    text = (ROOT / "docs" / "examples" / "probative-critique.yml").read_text()
    on = EXAMPLE[True] if True in EXAMPLE else EXAMPLE["on"]  # YAML reads `on` as a boolean
    assert "pull_request" in on and "pull_request_target" not in on
    assert EXAMPLE["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert re.search(r"^\s*-?\s*uses:\s*vedm1/probative@", text, re.MULTILINE)
    assert EXAMPLE["jobs"]["critique"]["timeout-minutes"] <= 60
    assert "cancel-in-progress" in text


def test_empty_inputs_fall_back_to_the_defaults_in_the_script() -> None:
    script = next(s for s in _steps() if "run" in s)["run"]
    for name in ("PATHS", "MAX_FILES", "MAX_MINUTES", "MAX_INLINE", "FAIL_ON"):
        assert f"${{PROBATIVE_{name}:-" in script


# --- PB35-p2 ---------------------------------------------------------------------------------

TARGET_PATH = ROOT / "docs" / "examples" / "probative-critique-target.yml"


def test_the_action_runs_outside_the_workspace_and_takes_a_label() -> None:
    run = next(s for s in _steps() if "run" in s)
    assert run["working-directory"] == "${{ runner.temp }}"  # a stray .env or uv.toml is not read
    assert ACTION["inputs"]["label"]["default"] == "probative-review"
    assert run["env"]["PROBATIVE_LABEL"] == "${{ inputs.label }}"
    assert "${PROBATIVE_LABEL:-" in run["run"] and "--label" in run["run"]


def test_the_target_example_is_least_privilege_and_never_checks_out_pr_code() -> None:
    text = TARGET_PATH.read_text()
    example = yaml.safe_load(text)
    on = example[True] if True in example else example["on"]
    assert set(on) == {"pull_request_target"}
    assert set(on["pull_request_target"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
        "labeled",
    }
    assert example["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert "actions/checkout" not in text
    assert "cancel-in-progress" in text
    # an unrelated label must not cancel the run a maintainer's label started
    assert "github.event.label.name" in example["concurrency"]["group"]
    for job in example["jobs"].values():
        for step in job["steps"]:
            assert "${{" not in step.get("run", "")
    assert re.search(r"^\s*-?\s*uses:\s*vedm1/probative@", text, re.MULTILINE)


def test_the_action_does_not_share_a_cache_on_a_secrets_bearing_event() -> None:
    setup = next(s for s in _steps() if "uses" in s)
    assert setup["with"]["enable-cache"] is False
