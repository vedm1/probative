"""No module outside `probative.llm` imports `litellm`.

This is the PB0 risk mitigation from PROBATIVE_BUILD_PLAN.md: LiteLLM's
abstraction must stay behind `probative.llm.Provider`, or agent code ends up
written against a specific vendor SDK's semantics by accident. This test
walks the actual source tree with `ast`, so it catches the leak regardless
of whether the leaking module happens to be imported (and therefore
executed) by the rest of the suite.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "probative"
ALLOWED_PACKAGE = SRC_ROOT / "llm"


def _names_litellm(name: str) -> bool:
    return name == "litellm" or name.startswith("litellm.")


def _imports_litellm(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(_names_litellm(alias.name) for alias in node.names):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and _names_litellm(node.module)
        ):
            return True
    return False


def test_no_module_outside_llm_package_imports_litellm() -> None:
    offenders: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        if ALLOWED_PACKAGE in path.parents or path.parent == ALLOWED_PACKAGE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _imports_litellm(tree):
            offenders.append(str(path.relative_to(SRC_ROOT.parent.parent)))

    assert not offenders, (
        f"litellm must only be imported inside probative.llm, but found it in: {offenders}"
    )


def test_litellm_provider_itself_does_import_it() -> None:
    # Sanity check on the test above: it should find *something* when pointed
    # at a file that does the import, so a bug that always returns "clean"
    # doesn't pass silently.
    path = ALLOWED_PACKAGE / "litellm_provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    assert _imports_litellm(tree)
