"""Probative — evidence-grounded product discovery.

Every claim in every artifact either traces to a source it came from or is
labelled a hypothesis with a test attached. See ``docs/DESIGN.md``.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("probative")
except PackageNotFoundError:  # pragma: no cover — running from a bare checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
