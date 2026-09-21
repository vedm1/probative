---
description: Start a disciplined build session for an Probative phase, spec-then-code with human in the loop
argument-hint: <phase e.g. PB1> [spec|implement]
---

You are starting a build session for **Probative** — an evidence-grounded, multi-agent product discovery system whose entire value proposition is that its output can be trusted. Arguments: `$ARGUMENTS`

First token is the phase code (`PB0`, `PB14`, `PB17-p2`…). Optional second token is `spec` or `implement`. Default to `spec` if no detailed implementation spec for this phase exists in `PROBATIVE_PHASE_SPECS.md`.

Follow this recipe exactly. **Do not skip steps. Do not write code before the plan is approved.** Generating code ahead of approval is the failure mode this workflow exists to prevent.

## 1. Prime context (read, don't assume)

- `CLAUDE.md` is already loaded. Honour it — especially **I4 (numbers are computed, never generated)**, **I6 (tedium budget)**, **I9 (forensic posture, onboarding mode)** and the **no-API-key test rule**. Those three are violated more often than the rest combined.
- Read the matching phase section in `PROBATIVE_PHASE_SPECS.md`, plus the shared specs S1–S4 it references.
- Read `PROBATIVE_BUILD_PLAN.md` for the sequencing rationale, the risks for this phase, and any open items that block it.
- Check predecessor phases are ✅ in `PHASES.md` — extract with `awk`, do not read the file whole.
- Read the **existing modules this phase touches**. Reuse the patterns that are there; do not build a parallel implementation of something that already exists.
- Check the open-items table. **Do not build on an unconfirmed assumption** — if an OI blocking this phase is still 🔲, say so and stop.
- If this phase adds a node or edge type, read the existing schema first. If it adds a formula, read the registry and the book citation it implements.

## 2. Play back understanding (required, before anything else)

State, before proposing anything:

- The objective in one sentence.
- What is in and out of scope **for this session**.
- Existing code you will reuse — actual paths and function names.
- New files, node types, formulas, agents or artifacts.
- **Which invariants this phase touches**, and how the implementation satisfies each.
- The gate story: what this phase unblocks, and what breaks downstream if it is wrong.
- Budget implications — token cost, run latency, and human interaction count if this phase adds any.
- Unresolved open items.

Surface tradeoffs. **Stop and ask** where the spec is thin. Most bad build sessions are visible as a wrong playback, and that is the cheapest place to catch them.

## 3. Branch by mode

**If `spec`** — produce a detailed implementation spec: final type names and field names, nullability, algorithms worked out in full, the interface contracts this phase exposes, and a test plan naming specific fixtures and assertions. For a phase adding a formula, include the worked example from the book it will be tested against. For a critic, include the rubric file and both fixture sets (S2). **Do not write code until the spec is approved.**

**If `implement`** (only after spec approval) — follow the approved spec. TDD: failing tests first, then inside-out — types and data → logic → interface. Surgical changes only.

Stack: Python 3.12+, `uv` for dependencies, `ruff` for lint and format, `pytest`, `mypy` strict on `core/` and `formulas/`. Source in `src/probative/`. LiteLLM only inside `src/probative/llm/`.

## 4. Plan and approve

Present a concrete, ordered plan: files to add and change, tests to write, order of operations. **Wait for approval. Do not edit before approval.**

## 5. Verify (do not declare done without this)

- `uv run pytest` passes **with no LLM credentials in the environment**, all new tests green.
- `uv run ruff check` clean. `uv run mypy src` passes.
- The phase's **gating check** from `PROBATIVE_PHASE_SPECS.md` passes — this is not the same thing as the test suite.
- If the phase adds a critic: it catches every seeded defect **and raises nothing on the clean fixture set**. Both numbers recorded.
- If the phase adds a formula: tested against the book's worked example, with the page cited in the test.
- If the phase adds provenance: the round-trip test passes — re-extraction reproduces the recorded text exactly.
- **For PB5–PB8, PB10, PB11, PB22, PB27, PB28, PB39, PB40: launch a subagent for independent review.** A fresh reader who was not anchored by the implementation. A green suite is not sufficient for these.

## 6. Document (close the loop)

- Flip this phase's row in `PHASES.md` 🔲 → ✅ and rewrite the Summary densely — files, types, formulas, endpoints, test counts, notable decisions. Write it for someone reading in six months with no memory of the session.
- If implementation revealed a better design than the spec, update `PROBATIVE_PHASE_SPECS.md`. Reconcile, do not drift.
- Append an **Implementation notes** block to the phase spec: what was discovered, what the spec got wrong, what a documented behaviour actually turned out to be, what remains stubbed and why.
- Resolve open items in `PROBATIVE_BUILD_PLAN.md` that this phase answered — writing out *how*, not just flipping the status. Add any new ones it surfaced.
- Update `CLAUDE.md` only if a durable fact changed: a new source of record, a confirmed contract, a new guardrail.

## Guardrails for a build session

- **Never ask a model for a number.** If a value belongs on a node, it has a `formula_id` and a registered pure function, or it does not exist. This is I4 and it is the one most likely to be violated under time pressure.
- **Never write a test that needs an API key to pass.** Record a fixture instead. CI runs on fork PRs with no secrets.
- **Never add a free-text slot to a renderer.** If an artifact needs to say something, that something is a node (I5).
- **Never let an agent write to the graph.** Agents propose patches; the `Committer` disposes (S1).
- **In onboarding mode, never evaluate a past decision or attribute fault to a person** (I9). State what appears to have been decided and what it rests on. `RedTeam` does not run in that mode — that is a config exclusion, not a prompt request.
- **Never assert a regulatory obligation the model inferred.** Constraints carry a source document and a locator, or they are a `Question` (I8).
- **Never add a step that asks a human to type what the system could derive and offer for confirmation** (I6).
- **One phase = one small PR.** If scope sprawls, stop and re-scope — slice as `-pN`, or open a new row. Never quietly absorb the extra work.
- If a guardrail blocks the obvious implementation, that is the guardrail working. Raise it; do not route around it.
