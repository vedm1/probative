"""PB34: the `doctor` tool. It reports what the *server* sees (its environment, working
directory and roots), never a key, a key length or a fragment of one, and makes no model call."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp.client import Client

from probative.interfaces.doctor import DoctorReport, diagnose, render_doctor
from probative.interfaces.mcp_server import build_server
from probative.llm.factory import PLUGIN_KEY_ENV
from tests.critique._scripted import Scripted

SECRET = "sk-test-SECRET-do-not-print-0123456789"
KEY = "ANTHROPIC_API_KEY"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "root"
    path.mkdir()
    return path


def _report(
    root: Path,
    environ: dict[str, str],
    cwd: Path | None = None,
    model: str = "anthropic/claude-sonnet-5",
) -> DoctorReport:
    return diagnose(
        environ=environ, roots=[root], default_out=root / "reports", cwd=cwd or root, model=model
    )


def _states(report: DoctorReport) -> dict[str, tuple[str, str]]:
    return {c.vendor: (c.state, c.source) for c in report.credentials}


def test_a_key_in_the_environment_is_set_from_the_environment(root: Path) -> None:
    report = _report(root, {KEY: SECRET})
    assert _states(report)["anthropic"] == ("set", "environment")
    assert _states(report)["openai"] == ("missing", "none")


def test_no_key_is_missing(root: Path) -> None:
    assert _states(_report(root, {}))["anthropic"] == ("missing", "none")


def test_an_unexpanded_placeholder_is_reported_as_a_placeholder(root: Path) -> None:
    report = _report(root, {KEY: "${ANTHROPIC_API_KEY}"})
    assert _states(report)["anthropic"] == ("placeholder", "none")


def test_a_dotenv_key_in_the_working_directory_is_found_and_the_file_is_named(
    root: Path,
) -> None:
    (root / ".env").write_text(f"ANTHROPIC_API_KEY={SECRET}\n", encoding="utf-8")
    report = _report(root, {})
    assert _states(report)["anthropic"] == ("set", "dotenv")
    assert report.dotenv == str(root / ".env")


def test_a_placeholder_in_the_environment_does_not_hide_a_dotenv_key(root: Path) -> None:
    (root / ".env").write_text(f"ANTHROPIC_API_KEY={SECRET}\n", encoding="utf-8")
    report = _report(root, {KEY: "${ANTHROPIC_API_KEY}"})
    assert _states(report)["anthropic"] == ("set", "dotenv")


def test_the_plugin_key_counts_only_when_nothing_else_is_set(root: Path) -> None:
    assert _states(_report(root, {PLUGIN_KEY_ENV: SECRET}))["anthropic"] == ("set", "plugin")
    assert _states(_report(root, {PLUGIN_KEY_ENV: SECRET, KEY: SECRET}))["anthropic"] == (
        "set",
        "environment",
    )
    unset = _report(root, {PLUGIN_KEY_ENV: "${user_config.api_key}"})
    assert _states(unset)["anthropic"] == ("placeholder", "none")


def test_no_dotenv_is_none(root: Path) -> None:
    assert _report(root, {}).dotenv is None


def test_readiness_follows_the_default_models_vendor(root: Path) -> None:
    assert _report(root, {KEY: SECRET}).ready is True
    assert _report(root, {}).ready is False
    assert _report(root, {"OPENAI_API_KEY": SECRET}).ready is False  # default model is anthropic


def test_roots_that_do_not_exist_or_allow_everything_are_flagged(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere"
    report = diagnose(
        environ={KEY: SECRET},
        roots=[missing, Path(Path.home().anchor), Path.home()],
        default_out=tmp_path / "reports",
        cwd=tmp_path,
        model="anthropic/claude-sonnet-5",
    )
    text = "\n".join(report.root_warnings)
    assert "does not exist" in text
    assert "filesystem root" in text
    assert "home directory" in text
    assert report.ready is False  # a root that allows everything is not a ready configuration


def test_the_rendering_never_contains_the_key_or_anything_derived_from_it(root: Path) -> None:
    (root / ".env").write_text(f"OPENAI_API_KEY={SECRET}\n", encoding="utf-8")
    text = render_doctor(_report(root, {KEY: SECRET, PLUGIN_KEY_ENV: SECRET}))
    assert SECRET not in text
    assert SECRET[:8] not in text
    assert str(len(SECRET)) not in text.replace(str(root), "")


def test_the_rendering_states_each_credential_and_the_verdict(root: Path) -> None:
    text = render_doctor(_report(root, {}))
    assert "anthropic: missing" in text
    assert "Ready: no" in text
    assert "/probative:setup" in text
    assert str(root) in text
    ready = render_doctor(_report(root, {KEY: SECRET}))
    assert "anthropic: set (from environment)" in ready
    assert "Ready: yes" in ready


def test_the_tool_is_served_and_reads_the_servers_own_environment(root: Path) -> None:
    class Spy(Scripted):
        pass

    provider = Spy()
    server: Any = build_server(
        lambda model: provider,
        roots=[root],
        default_out=root / "reports",
        environ={KEY: SECRET},
    )

    async def go() -> str:
        async with Client(server) as client:
            result = await client.call_tool("doctor", {})
            assert not result.is_error
            return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")

    text = asyncio.run(go())
    assert "anthropic: set (from environment)" in text
    assert SECRET not in text
    assert provider.judge_batches == []  # no model call


def test_the_tool_takes_no_arguments(root: Path) -> None:
    server: Any = build_server(lambda m: Scripted(), roots=[root], default_out=root / "r")

    async def go() -> Any:
        async with Client(server) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    tools = asyncio.run(go())
    assert tools["doctor"].input_schema.get("properties", {}) == {}


# --- review findings (PB34 independent review) ----------------------------------------------


def test_a_lowercase_dotenv_key_is_found_as_settings_finds_it(root: Path) -> None:
    (root / ".env").write_text(f"anthropic_api_key={SECRET}\n", encoding="utf-8")
    assert _states(_report(root, {}))["anthropic"] == ("set", "dotenv")


def test_an_undecodable_dotenv_is_reported_not_raised_and_leaks_nothing(root: Path) -> None:
    (root / ".env").write_bytes(b"ANTHROPIC_API_KEY=" + SECRET.encode() + b"\xff\xfe\n")
    report = _report(root, {})
    assert report.dotenv_unreadable is True and report.ready is False
    text = render_doctor(report)
    assert ".env" in text and "unreadable" in text
    assert "0xff" not in text and "position" not in text and SECRET not in text


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode 000 file")
def test_an_unreadable_dotenv_by_permission_is_reported_not_raised(root: Path) -> None:
    env = root / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={SECRET}\n", encoding="utf-8")
    env.chmod(0)
    try:
        report = _report(root, {})
    finally:
        env.chmod(0o600)
    assert report.dotenv_unreadable is True and report.ready is False


def test_a_dotenv_that_is_a_directory_is_not_a_dotenv(root: Path) -> None:
    (root / ".env").mkdir()
    report = _report(root, {})
    assert report.dotenv is None and report.dotenv_unreadable is False


def test_a_model_without_a_provider_prefix_is_not_ready(root: Path) -> None:
    report = _report(root, {KEY: SECRET}, model="gpt-4o")
    assert report.default_vendor is None and report.ready is False
    assert "provider prefix" in render_doctor(report)


def test_a_vendor_that_needs_no_key_is_ready_and_says_it_was_not_checked(root: Path) -> None:
    report = _report(root, {}, model="ollama/llama3")
    assert report.default_vendor == "ollama" and report.ready is True
    assert "no key check for ollama" in render_doctor(report)


def test_the_model_a_server_was_built_with_is_the_model_doctor_reports(root: Path) -> None:
    from probative.critique import CritiqueOptions

    server: Any = build_server(
        lambda m: Scripted(),
        roots=[root],
        default_out=root / "r",
        environ={},
        base_options=CritiqueOptions(model="openai/gpt-5"),
    )

    async def go() -> str:
        async with Client(server) as client:
            result = await client.call_tool("doctor", {})
            return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")

    assert "Default model: openai/gpt-5" in asyncio.run(go())


@pytest.fixture
def restore_environ() -> Iterator[None]:
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


_VALUES = {"real": SECRET, "placeholder": "${X}", "missing": None}


@pytest.mark.parametrize("env", list(_VALUES))
@pytest.mark.parametrize("dotenv", list(_VALUES))
@pytest.mark.parametrize("plugin", list(_VALUES))
@pytest.mark.parametrize("key_name", ["ANTHROPIC_API_KEY", "anthropic_api_key"])
def test_doctor_and_make_provider_agree_in_every_combination(
    restore_environ: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    env: str,
    dotenv: str,
    plugin: str,
    key_name: str,
) -> None:
    """The review's parity check: whatever `doctor` calls ready for anthropic is exactly what
    `make_provider` accepts, for every mix of environment, `.env` and plugin key."""
    from probative.config import MissingCredentialsError
    from probative.llm.factory import make_provider

    for name in (KEY, "OPENAI_API_KEY", "GEMINI_API_KEY", PLUGIN_KEY_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    environ: dict[str, str] = {}
    if _VALUES[env] is not None:
        environ[KEY] = str(_VALUES[env])
        monkeypatch.setenv(KEY, environ[KEY])
    if _VALUES[plugin] is not None:
        environ[PLUGIN_KEY_ENV] = str(_VALUES[plugin])
        monkeypatch.setenv(PLUGIN_KEY_ENV, environ[PLUGIN_KEY_ENV])
    if _VALUES[dotenv] is not None:
        (tmp_path / ".env").write_text(f"{key_name}={_VALUES[dotenv]}\n", encoding="utf-8")

    reported = diagnose(
        environ=environ,
        roots=[tmp_path],
        default_out=tmp_path / "r",
        cwd=tmp_path,
        model="anthropic/claude-sonnet-5",
    )
    try:
        make_provider("anthropic/claude-sonnet-5")
        accepted = True
    except MissingCredentialsError:
        accepted = False
    assert reported.ready is accepted, (env, dotenv, plugin, key_name)
