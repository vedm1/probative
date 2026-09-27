"""Load and validate a rubric YAML file (S2)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from probative.core.critic import MalformedRubricError, Rubric, RubricNotFoundError


def load_rubric(path: Path) -> Rubric:
    """Parse and validate one rubric YAML file.

    Raises `RubricNotFoundError` if `path` does not exist, `MalformedRubricError`
    if the file is not valid YAML, is not a mapping at the top level, or fails
    `Rubric`'s schema.
    """
    if not path.is_file():
        raise RubricNotFoundError(path, "rubric file not found")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise MalformedRubricError(path, f"invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise MalformedRubricError(path, "rubric document must be a YAML mapping")
    try:
        return Rubric.model_validate(raw)
    except ValidationError as exc:
        raise MalformedRubricError(path, f"schema violation: {exc}") from exc


def resolve_fixture_paths(rubric: Rubric, rubric_path: Path) -> tuple[list[Path], list[Path]]:
    """Resolve `rubric.clean_fixtures`/`defect_fixtures` — globs relative to
    `rubric_path`'s directory — to sorted lists of actual paths.

    An empty match is not an error here: fixtures are a test-time concern,
    and a rubric can be loaded in a production install with no fixtures on
    disk at all. Only `probative.critics.testing.assert_rubric_fixtures`
    treats an empty match as a failure.
    """
    base = rubric_path.parent
    clean = sorted(base.glob(rubric.clean_fixtures))
    defect = sorted(base.glob(rubric.defect_fixtures))
    return clean, defect
