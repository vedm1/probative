"""PB34: the Claude Code / Cowork plugin skin. Thin by construction: the plugin is a manifest,
three commands and a skill; every behaviour is in the MCP server. These tests keep it that
way and keep it wired to the server's real tool names. No key is needed (the one test that
launches the server through `uvx` skips when `uvx` is absent and needs the package index)."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp.client import Client

from probative.interfaces.mcp_server import build_server
from probative.llm.factory import PLUGIN_KEY_ENV
from tests.critique._scripted import Scripted

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
COMMANDS = REPO / "commands"
SKILL = REPO / "skills" / "probative-critique" / "SKILL.md"
PLUGIN = "probative"
SERVER = "probative"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _registered_tools(tmp_path: Path) -> list[str]:
    server: Any = build_server(lambda m: Scripted(), roots=[tmp_path], default_out=tmp_path / "r")

    async def go() -> list[str]:
        async with Client(server) as client:
            return [t.name for t in (await client.list_tools()).tools]

    return asyncio.run(go())


def _full(tool: str) -> str:
    return f"mcp__plugin_{PLUGIN}_{SERVER}__{tool}"


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name} has no frontmatter"
    head, _, body = text[4:].partition("\n---\n")
    fields: dict[str, str] = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, body


def _plugin_texts() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in [*COMMANDS.glob("*.md"), SKILL]}


# --- manifest and marketplace ------------------------------------------------------------


def test_the_manifest_names_the_plugin_and_declares_the_server_inline() -> None:
    manifest = _json(MANIFEST)
    assert manifest["name"] == PLUGIN
    assert manifest["author"]["name"]
    assert manifest["description"]
    assert set(manifest["mcpServers"]) == {SERVER}  # inline: no root .mcp.json for contributors
    assert not (REPO / ".mcp.json").exists()


def test_the_server_launches_the_published_extra_with_uvx() -> None:
    server = _json(MANIFEST)["mcpServers"][SERVER]
    assert server["command"] == "uvx"
    assert server["args"] == ["--from", "probative[mcp]", "probative", "mcp"]


def test_the_server_command_exists_in_the_cli() -> None:
    from typer.testing import CliRunner

    from probative.cli import app

    assert CliRunner().invoke(app, ["mcp", "--help"]).exit_code == 0


def test_the_key_is_a_sensitive_option_delivered_under_a_dedicated_name() -> None:
    manifest = _json(MANIFEST)
    option = manifest["userConfig"]["api_key"]
    assert option["sensitive"] is True
    assert option["required"] is False  # a user who already exports the key is not blocked
    env = manifest["mcpServers"][SERVER]["env"]
    # never ANTHROPIC_API_KEY: an unset option must not overwrite a key the user exports
    assert env == {PLUGIN_KEY_ENV: "${user_config.api_key}"}


def test_the_marketplace_points_at_this_directory() -> None:
    marketplace = _json(MARKETPLACE)
    assert marketplace["name"] == PLUGIN
    [entry] = marketplace["plugins"]
    assert entry["name"] == PLUGIN and entry["source"] == "./"
    assert (REPO / entry["source"] / ".claude-plugin" / "plugin.json").is_file()


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_claude_validates_the_plugin_and_the_marketplace() -> None:
    """Not `--strict`: a plugin at the repository root also contains this repository's own
    CLAUDE.md, which the validator warns about. That is the only warning allowed."""
    for target in (REPO, MARKETPLACE):
        done = subprocess.run(
            ["claude", "plugin", "validate", str(target)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = done.stdout + done.stderr
        assert done.returncode == 0 and "✘" not in output, output
        warnings = [line for line in output.splitlines() if " root: " in line]
        assert all("CLAUDE.md" in line for line in warnings), output


# --- commands name only real tools ---------------------------------------------------------


def test_the_commands_exist_and_each_allows_exactly_one_real_tool(tmp_path: Path) -> None:
    registered = set(_registered_tools(tmp_path))
    expected = {"critique": "critique", "doctor": "doctor", "setup": "doctor"}
    assert {p.stem for p in COMMANDS.glob("*.md")} == set(expected)
    for command, tool in expected.items():
        assert tool in registered
        fields, _ = _frontmatter(COMMANDS / f"{command}.md")
        assert fields["description"]
        assert fields["allowed-tools"] == _full(tool), command


def test_the_critique_command_takes_a_path() -> None:
    fields, body = _frontmatter(COMMANDS / "critique.md")
    assert "path" in fields["argument-hint"]
    assert "$ARGUMENTS" in body


# --- thin by construction ----------------------------------------------------------------------


def test_no_text_carries_a_number_the_server_did_not_compute() -> None:
    for name, text in _plugin_texts().items():
        assert not re.search(r"\d", text), f"{name} contains a digit"


def test_no_text_contains_a_key_shaped_string() -> None:
    for name, text in _plugin_texts().items():
        assert not re.search(r"sk-[A-Za-z0-9_-]{8,}", text), name


def test_critique_and_doctor_relay_verbatim_and_add_nothing() -> None:
    for name in ("critique.md", "doctor.md"):
        _, body = _frontmatter(COMMANDS / name)
        assert "verbatim" in body, name
        for banned in ("summarise", "summarize", "rephrase", "score it", "estimate"):
            assert banned not in body.lower() or f"do not {banned}" in body.lower(), (name, banned)


def test_the_skill_states_the_rules_that_protect_the_output() -> None:
    fields, body = _frontmatter(SKILL)
    assert fields["name"] == "probative-critique" and fields["description"]
    lowered = body.lower()
    assert "verbatim" in lowered
    assert "a block is a block" in lowered
    assert "never invent" in lowered and "citation" in lowered
    assert "onboarding" in lowered
    assert "count" in lowered and "score" in lowered  # told not to compute or restate them


def test_setup_never_takes_the_key_in_chat() -> None:
    _, body = _frontmatter(COMMANDS / "setup.md")
    lowered = body.lower()
    assert "/plugin configure" in lowered
    assert "never ask" in lowered and "in chat" in lowered
    assert "transcript" in lowered and "rotate" in lowered  # what to say if one is pasted anyway
    assert "doctor" in lowered


# --- launch equivalence ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("uvx") is None, reason="uvx not installed")
def test_the_manifest_command_with_the_extra_from_this_checkout_serves_both_tools(
    tmp_path: Path,
) -> None:
    """Proves everything except PyPI resolution, which cannot be tested before the first release."""
    from mcp.client.stdio import StdioServerParameters

    server = _json(MANIFEST)["mcpServers"][SERVER]
    args = [f"{REPO}[mcp]" if a == "probative[mcp]" else a for a in server["args"]]
    params = StdioServerParameters(
        command=server["command"], args=args, cwd=tmp_path, env=_clean_env()
    )

    async def go() -> list[str]:
        async with Client(params) as client:
            return [t.name for t in (await client.list_tools()).tools]

    assert asyncio.run(go()) == ["critique", "doctor"]


def _clean_env() -> dict[str, str]:
    import os

    keep = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    return keep
