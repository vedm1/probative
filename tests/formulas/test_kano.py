"""Kano's evaluation table (Berger et al. 1993, p. 6; Olsen p. 64 names the classes).

The grid below was checked against Berger et al. by the owner (2026-11-05). If a
cell is ever shown to be wrong, fix it here and in `probative.formulas.kano`
together; the cell tests are the specification.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest

from probative.formulas import REGISTRY
from probative.formulas.kano import (
    KanoAnswer,
    KanoCategory,
    UnknownKanoAnswerError,
    kano_classify,
    node_class,
)

L, M, N, W, D = (
    KanoAnswer.LIKE,
    KanoAnswer.MUST_BE,
    KanoAnswer.NEUTRAL,
    KanoAnswer.LIVE_WITH,
    KanoAnswer.DISLIKE,
)
ANSWERS = (L, M, N, W, D)

# An independent copy of the grid, written row by row: rows are the functional
# answer, columns the dysfunctional answer, both in the order like, must_be,
# neutral, live_with, dislike.
GRID = {
    L: "Q A A A O",
    M: "R I I I M",
    N: "R I I I M",
    W: "R I I I M",
    D: "R R R R Q",
}
LETTER = {
    "A": KanoCategory.ATTRACTIVE,
    "O": KanoCategory.ONE_DIMENSIONAL,
    "M": KanoCategory.MUST_BE,
    "I": KanoCategory.INDIFFERENT,
    "R": KanoCategory.REVERSE,
    "Q": KanoCategory.QUESTIONABLE,
}
CELLS = [
    (f, d, LETTER[letter])
    for f, row in GRID.items()
    for d, letter in zip(ANSWERS, row.split(), strict=True)
]


@pytest.mark.parametrize(("functional", "dysfunctional", "want"), CELLS, ids=lambda x: str(x))
def test_every_cell_of_the_evaluation_table(
    functional: KanoAnswer, dysfunctional: KanoAnswer, want: KanoCategory
) -> None:
    assert kano_classify(functional, dysfunctional) == want


def test_the_grid_has_25_cells_and_every_pair_is_classified() -> None:
    assert len(CELLS) == 25
    for f, d in itertools.product(ANSWERS, ANSWERS):
        assert isinstance(kano_classify(f, d), KanoCategory)


def test_questionable_is_only_like_like_and_dislike_dislike() -> None:
    q = {
        (f, d)
        for f, d in itertools.product(ANSWERS, ANSWERS)
        if kano_classify(f, d) == KanoCategory.QUESTIONABLE
    }
    assert q == {(L, L), (D, D)}


def test_every_category_is_reachable() -> None:
    got = {kano_classify(f, d) for f, d in itertools.product(ANSWERS, ANSWERS)}
    assert got == set(KanoCategory)


def test_the_book_examples_p64_65() -> None:
    # A seat belt: expected when present, hated when absent -> must-have.
    assert kano_classify(M, D) == KanoCategory.MUST_BE
    # Fuel economy: liked when present, disliked when absent -> performance.
    assert kano_classify(L, D) == KanoCategory.ONE_DIMENSIONAL
    # A cup holder in 1980s minivans: liked when present, no complaint when absent -> delighter.
    assert kano_classify(L, N) == KanoCategory.ATTRACTIVE


@pytest.mark.parametrize(
    ("category", "want"),
    [
        (KanoCategory.MUST_BE, "must_have"),
        (KanoCategory.ONE_DIMENSIONAL, "performance"),
        (KanoCategory.ATTRACTIVE, "delighter"),
        (KanoCategory.INDIFFERENT, "indifferent"),
        (KanoCategory.REVERSE, "reverse"),
        (KanoCategory.QUESTIONABLE, None),
    ],
)
def test_node_class_maps_to_the_graph_classes(category: KanoCategory, want: str | None) -> None:
    assert node_class(category) == want


def test_node_class_values_are_the_kanoclass_literals() -> None:
    from typing import get_args

    from probative.core.graph.nodes import KanoClass

    allowed = set(get_args(KanoClass.model_fields["classification"].annotation))
    produced = {node_class(c) for c in KanoCategory} - {None}
    assert produced == allowed


@pytest.mark.parametrize("bad", ["like", "LIKE", "", None, 3])
def test_a_malformed_answer_is_a_typed_error(bad: object) -> None:
    with pytest.raises(UnknownKanoAnswerError):
        kano_classify(bad, L)  # type: ignore[arg-type]
    with pytest.raises(UnknownKanoAnswerError):
        kano_classify(L, bad)  # type: ignore[arg-type]


def test_it_is_not_a_registered_formula_and_builds_no_computed() -> None:
    assert "kano_classify" not in REGISTRY
    source = Path(__file__).parents[2] / "src" / "probative" / "formulas" / "kano.py"
    names = {
        n.id if isinstance(n, ast.Name) else n.attr
        for n in ast.walk(ast.parse(source.read_text()))
        if isinstance(n, ast.Name | ast.Attribute)
    }
    imported = {
        a.name
        for n in ast.walk(ast.parse(source.read_text()))
        if isinstance(n, ast.ImportFrom)
        for a in n.names
    }
    assert "Computed" not in names | imported
