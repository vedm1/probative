"""The package and every subpackage import cleanly, with no credentials."""

from __future__ import annotations

import importlib


def test_package_imports() -> None:
    import probative

    assert probative.__version__


def test_every_subpackage_imports() -> None:
    subpackages = [
        "probative.core",
        "probative.agents",
        "probative.graph_runtime",
        "probative.render",
        "probative.exporters",
        "probative.interfaces",
        "probative.llm",
        "probative.formulas",
        "probative.config",
        "probative.cli",
    ]
    for name in subpackages:
        importlib.import_module(name)
