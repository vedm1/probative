"""Configuration loads with no environment variables set.

A missing credential is a typed error raised when something asks for it —
never a crash at import or settings-construction time.
"""

from __future__ import annotations

import pytest

from probative.config import MissingCredentialsError, Settings


def test_settings_load_with_empty_environment(tmp_path, monkeypatch) -> None:
    # No .env file to find, no *_API_KEY set (conftest's autouse fixture
    # already scrubs those) — construction must still succeed.
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.anthropic_api_key is None
    assert settings.openai_api_key is None
    assert settings.gemini_api_key is None


def test_missing_credential_is_a_typed_error_not_a_crash(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()

    with pytest.raises(MissingCredentialsError) as exc_info:
        settings.credential_for("anthropic")

    assert exc_info.value.provider == "anthropic"
    assert "anthropic" in str(exc_info.value)


def test_configured_credential_is_returned() -> None:
    settings = Settings(anthropic_api_key="sk-test-not-a-real-key")

    credential = settings.credential_for("anthropic")

    assert credential.get_secret_value() == "sk-test-not-a-real-key"


def test_unknown_provider_raises_missing_credentials_error() -> None:
    settings = Settings()

    with pytest.raises(MissingCredentialsError):
        settings.credential_for("some-provider-nobody-configured")
