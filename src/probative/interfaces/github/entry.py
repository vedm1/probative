"""`probative github-review`: the Actions environment in, an exit code out (PB35).

The trust decision runs before any provider is built, so a fork pull request (which has no
secret) never needs one. Misconfiguration and infrastructure failures are workflow
annotations that follow `fail-on`: green by default, red only when the team asked for a gate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from probative.config import MissingCredentialsError, Settings
from probative.critique.pipeline import CritiqueOptions
from probative.interfaces.github.api import GitHubClient
from probative.interfaces.github.context import ContextError, load_context
from probative.interfaces.github.runner import ActionOptions, annotate, run_review
from probative.interfaces.github.trust import decide
from probative.llm import Provider

DEFAULT_API_URL = "https://api.github.com"


def api_url(environ: Mapping[str, str]) -> str:
    return environ.get("GITHUB_API_URL") or DEFAULT_API_URL


def run_from_env(
    environ: Mapping[str, str],
    options: ActionOptions,
    *,
    provider_factory: Callable[[str], Provider],
    echo: Callable[[str], None],
    model: str | None = None,
    critique_options: CritiqueOptions | None = None,
) -> int:
    strict = 2 if options.fail_on == "block" else 0

    def warn(message: str) -> int:
        echo(annotate("warning", message))
        return strict

    token = environ.get("GITHUB_TOKEN", "").strip()
    event_path = environ.get("GITHUB_EVENT_PATH", "")
    if not token:
        return warn("GITHUB_TOKEN is not set; pass it to the action with `github-token`")
    if not event_path:
        return warn("GITHUB_EVENT_PATH is not set; this command runs inside GitHub Actions")
    try:
        ctx = load_context(Path(event_path), environ.get("GITHUB_EVENT_NAME", ""))
    except ContextError as error:
        return warn(str(error))
    decision = decide(ctx)
    if not decision.allowed:
        echo(annotate("notice", decision.reason))
        return 0
    model_id = model or Settings().model
    try:
        provider = provider_factory(model_id)
    except MissingCredentialsError:
        return warn("no model API key is available; add it as a repository secret and pass it in")
    except Exception as error:  # never put the text of a provider error in a log
        return warn(f"could not start the model provider ({type(error).__name__})")
    result = run_review(
        ctx,
        GitHubClient(api_url(environ), token),
        options,
        provider=provider,
        critique_options=critique_options or CritiqueOptions(model=model_id),
    )
    for message in result.messages:
        echo(message)
    echo(
        f"Probative reviewed {result.reviewed} file(s), posted {result.inline_posted} inline "
        f"comment(s), skipped {len(result.skipped)}."
    )
    return result.exit_code
