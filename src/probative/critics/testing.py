"""S2's fixture contract, made runnable: a rubric names a clean fixture set
a critic must raise nothing on, and a defect fixture set it must catch
every one of. Every critic phase (PB5 onward) calls this from its own
tests.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel

from probative.critics.base import Critic
from probative.critics.rubric import resolve_fixture_paths


def assert_rubric_fixtures(
    critic: Critic,
    rubric_path: Path,
    parse_fixture: Callable[[Path], Sequence[BaseModel]],
) -> None:
    """Run `critic` against every fixture its own rubric declares.

    Raises `AssertionError` immediately if either the `clean_fixtures` or
    `defect_fixtures` glob matched zero files — a fixture-authoring bug,
    not a critic bug. Then asserts `critic.check(...)` returns `[]` for
    every clean fixture and a non-empty list for every seeded-defect
    fixture.

    `parse_fixture` turns one fixture file into typed candidates; it is
    supplied by the caller because that requires knowing the candidate
    type this critic checks, which this framework does not — that
    knowledge lives with each critic phase's own tests.
    """
    clean_paths, defect_paths = resolve_fixture_paths(critic.rubric, rubric_path)
    if not clean_paths:
        raise AssertionError(f"{rubric_path}: clean_fixtures glob matched no files")
    if not defect_paths:
        raise AssertionError(f"{rubric_path}: defect_fixtures glob matched no files")
    for path in clean_paths:
        findings = critic.check(parse_fixture(path))
        assert not findings, f"{path}: expected no findings on a clean fixture, got {findings}"
    for path in defect_paths:
        findings = critic.check(parse_fixture(path))
        assert findings, f"{path}: expected at least one finding on a seeded-defect fixture"
