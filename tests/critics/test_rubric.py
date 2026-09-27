from __future__ import annotations

import pytest

from probative.core.critic import MalformedRubricError, RubricNotFoundError, Severity
from probative.critics.rubric import load_rubric, resolve_fixture_paths
from tests.critics._paths import FIXTURES

RUBRIC_PATH = FIXTURES / "example" / "rubric.yaml"
MALFORMED = FIXTURES / "malformed"


def test_load_rubric_happy_path() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    assert rubric.id == "non_empty_text"
    assert rubric.severity == Severity.WARN
    assert rubric.invariant is None
    assert rubric.applies_to == ["Note"]
    assert len(rubric.checks) == 1
    check = rubric.checks[0]
    assert check.id == "non_empty_text"
    assert check.description
    assert check.examples_bad == [""]
    assert check.examples_good == ["a real note"]
    assert check.remedy == "Fill in the note's text"
    assert rubric.clean_fixtures == "fixtures/clean/*.json"
    assert rubric.defect_fixtures == "fixtures/seeded/*.json"


def test_load_rubric_missing_file() -> None:
    missing = FIXTURES / "example" / "does_not_exist.yaml"
    with pytest.raises(RubricNotFoundError) as exc_info:
        load_rubric(missing)
    assert str(missing) in str(exc_info.value)


def test_load_rubric_invalid_yaml_syntax() -> None:
    with pytest.raises(MalformedRubricError):
        load_rubric(MALFORMED / "invalid_syntax.yaml")


def test_load_rubric_not_a_mapping() -> None:
    with pytest.raises(MalformedRubricError):
        load_rubric(MALFORMED / "not_a_mapping.yaml")


def test_load_rubric_missing_required_field() -> None:
    with pytest.raises(MalformedRubricError):
        load_rubric(MALFORMED / "missing_field.yaml")


def test_load_rubric_invalid_severity_enum() -> None:
    with pytest.raises(MalformedRubricError):
        load_rubric(MALFORMED / "bad_severity.yaml")


def test_resolve_fixture_paths() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    clean, defect = resolve_fixture_paths(rubric, RUBRIC_PATH)
    assert len(clean) == 2
    assert len(defect) == 2
    assert clean == sorted(clean)
    assert defect == sorted(defect)


def test_resolve_fixture_paths_no_match_is_not_an_error() -> None:
    rubric = load_rubric(RUBRIC_PATH)
    no_match_rubric = rubric.model_copy(update={"clean_fixtures": "fixtures/clean/nope_*.json"})
    clean, defect = resolve_fixture_paths(no_match_rubric, RUBRIC_PATH)
    assert clean == []
    assert len(defect) == 2
