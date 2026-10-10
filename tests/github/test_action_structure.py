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
