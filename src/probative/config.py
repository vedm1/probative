"""Configuration: environment variables, with `.env` for local development.

`.env` is gitignored; `.env.example` documents the keys. Loading configuration
must never crash on an empty environment — a missing credential is reported as
a typed error at the point it is needed, not as a startup failure. This is
what lets the default test suite run with zero LLM credentials present (S3).
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingCredentialsError(Exception):
    """Raised when a provider is used but no credential for it is configured.

    Not raised at settings-load time — only when something actually needs
    the credential. Loading `Settings()` with no environment variables set
    must always succeed.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"No credentials configured for provider {provider!r}. "
            f"Set the corresponding *_API_KEY environment variable "
            f"(see .env.example)."
        )


class Settings(BaseSettings):
    """Process configuration, loaded from the environment and `.env`.

    Every field is optional at load time. A run that needs a provider it has
    no key for fails loudly and specifically via `credential_for`, not via an
    attribute access on `None`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

    # The default model for the provider adapter (`probative.llm`).
    model: str = "anthropic/claude-sonnet-5"

    def credential_for(self, provider: str) -> SecretStr:
        """Return the configured credential for `provider`.

        Raises `MissingCredentialsError` if it is not set — the only place
        an unconfigured provider becomes an error.
        """
        credentials: dict[str, SecretStr | None] = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
        }
        value = credentials.get(provider)
        if value is None:
            raise MissingCredentialsError(provider)
        return value
