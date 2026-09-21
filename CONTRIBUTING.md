# Contributing to Probative

Thanks for the interest. This project runs on a small number of
non-negotiable guardrails — read [`CLAUDE.md`](CLAUDE.md) before your first
PR, it's short and it's the actual review checklist.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
git clone https://github.com/vedm1/probative.git
cd probative
uv sync --all-groups
uv run pre-commit install
```

## Before opening a PR

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
```

`pytest` must pass with **no LLM credentials in your environment** — the
repository is public and CI on a fork PR has no secrets. If you're adding a
test that exercises an agent or the LLM adapter, record a fixture rather than
depending on a live call (see `tests/llm/` for the pattern; live-only tests
are marked `@pytest.mark.live` and excluded from the default run).

## The guardrails that matter most

- **Numbers are computed, never generated (I4).** If a numeric field belongs
  on a node, it has a `formula_id` pointing at a registered pure function in
  `probative.formulas`. An LLM may propose formula *inputs*; it may never
  produce an *output*.
- **Agents never mutate the graph.** They return a proposed patch; the
  `Committer` applies it only after validators and critics pass.
- **No free-text slots in renderers (I5).** If an artifact needs to say
  something, that something is a node in the graph.

The full list is in `CLAUDE.md`.

## The easiest first contribution: a critic

A critic is a rubric file (data, not prose buried in a prompt) plus one
class with one method. See the rubric format in
`PROBATIVE_PHASE_SPECS.md` (S2) once PB3 lands. Every critic ships with a
clean fixture set it must raise nothing on, and a defect fixture set it must
catch — the false-positive requirement is not optional.

## Commit messages

Plain, descriptive, present tense. No enforced convention beyond that yet.
