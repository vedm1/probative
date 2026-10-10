"""PB34: what counts as "a key is configured". A client that cannot expand `${VAR}` may hand
the server the literal placeholder; that must read as missing, not as a key the provider
will reject with an authentication error."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from probative.config import MissingCredentialsError
from probative.llm.factory import PLUGIN_KEY_ENV, credential_state, make_provider

KEY = "ANTHROPIC_API_KEY"
MODEL = "anthropic/claude-sonnet-5"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    saved = dict(os.environ)  # make_provider exports keys into os.environ directly
    for name in (KEY, "OPENAI_API_KEY", "GEMINI_API_KEY", PLUGIN_KEY_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env
    yield
    os.environ.clear()
    os.environ.update(saved)


def test_credential_state_reads_set_missing_and_placeholder() -> None:
    assert credential_state("anthropic", {KEY: "sk-real"}) == "set"
    assert credential_state("anthropic", {}) == "missing"
    assert credential_state("anthropic", {KEY: ""}) == "missing"
    assert credential_state("anthropic", {KEY: "   "}) == "missing"
    assert credential_state("anthropic", {KEY: "${ANTHROPIC_API_KEY}"}) == "placeholder"
    assert credential_state("anthropic", {KEY: "${user_config.api_key}"}) == "placeholder"


def test_a_vendor_with_no_key_variable_is_missing() -> None:
    assert credential_state("ollama", {"ANTHROPIC_API_KEY": "sk-real"}) == "missing"


def test_a_placeholder_key_is_missing_credentials_not_a_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(KEY, "${ANTHROPIC_API_KEY}")
    with pytest.raises(MissingCredentialsError):
        make_provider(MODEL)


def test_a_placeholder_in_the_environment_does_not_shadow_a_dotenv_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv(KEY, "${ANTHROPIC_API_KEY}")
    make_provider(MODEL)
    assert os.environ[KEY] == "sk-from-dotenv"


def test_the_plugin_key_is_used_only_when_no_real_key_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PLUGIN_KEY_ENV, "sk-from-plugin")
    make_provider(MODEL)
    assert os.environ[KEY] == "sk-from-plugin"

    monkeypatch.setenv(KEY, "sk-from-shell")
    make_provider(MODEL)
    assert os.environ[KEY] == "sk-from-shell"  # a real key in the environment wins


def test_an_unconfigured_plugin_key_placeholder_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PLUGIN_KEY_ENV, "${user_config.api_key}")
    with pytest.raises(MissingCredentialsError):
        make_provider(MODEL)
