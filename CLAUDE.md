# CLAUDE.md — Probative Development Rules

Read this before touching code. These are non-negotiable guardrails, not style preferences.

Probative is an evidence-grounded, multi-agent product discovery system. Its entire value proposition is that its output can be trusted. Every rule below exists to protect that.

Full design rationale: `docs/DESIGN.md`. Phase tracker: `PHASES.md`.

---

## Process rules

**Think before coding.** Read the phase spec, the build plan and the modules the phase touches before proposing anything. Building a parallel implementation of something that already exists is the most common failure in a multi-session project, and it is always caused by not reading first.

**Surgical changes.** Touch only what this phase needs. A phase that edits eleven files it did not need to edit cannot be reviewed, and its blast radius is unknowable.

**TDD.** Failing tests first, then build inside-out: types and data → logic → interface. In this project the tests are not a safety net, they are the specification — a formula with no test against the book's worked example is not implemented.

**Document what you create.** A phase is not done when the code works. It is done when `PHASES.md`, the phase spec and the open-items table describe what actually exists.

---

## The nine non-negotiable guardrails

These are the invariants from `docs/DESIGN.md` §4. Each is enforced by a validator, not by good intentions. If a guardrail blocks the obvious implementation, that is the guardrail working — raise it, do not route around it.

### I1 — No orphan claims

- Every `Claim` node carries at least one `EVIDENCED_BY` edge, or is typed `Hypothesis`.
- There is no third category. A claim with no evidence and no hypothesis type is a validation error, not a warning.
- `EvidenceSpan` must resolve: source id, byte offsets, and re-extraction must reproduce the recorded text.

### I2 — Every hypothesis is falsifiable

- A `Hypothesis` without a `TESTED_BY` edge to a `Test` is a validation error.
- A `Test` states method, cost, duration and a **kill criterion written before the test runs**.
- "We'll validate this later" is not a test.

### I3 — Problem space and solution space never mix

- A `Need` is a customer benefit: verb-first, customer voice, precise enough to measure (Olsen p. 39).
- A `Need` containing solution grammar — a feature name, a UI noun, an implementation verb — is rejected by `SpaceWarden`.
- `FeatureIdea` may reference a `Need`. A `Need` may never reference a `FeatureIdea`.

### I4 — Numbers are computed, never generated

**The single most important rule in the codebase.**

- Every numeric field on every node declares a `formula_id` pointing at a registered pure function in `probative.formulas`.
- `FormulaValidator` recomputes every numeric field on commit and diffs it. A mismatch fails the commit.
- An LLM may propose formula **inputs**. It may never produce an **output**.
- If you find yourself writing a prompt that asks a model for a score, stop. That score has a formula, or it should not exist.

### I5 — Every artifact is a projection

- Renderers have no free-text slots. There is no place in a template for prose the graph does not contain.
- If an artifact needs to say something, that something is a node.
- This is what makes artifacts unable to rot independently of the graph.

### I6 — Tedium budget

- Every human interaction is a **decision**, never transcription. Accept / reject / amend on a proposed patch. Never a blank page.
- The system never asks a human to type what it can derive and offer for confirmation.
- Phase interaction budgets are in `docs/DESIGN.md` §9.5 and are measured by `TediumAuditor`.
- A feature that requires work from a *beneficiary* — an engineer, an EM, a designer — is an I6 violation dressed up as collaboration.

### I7 — Baseline integrity

- A gate commit produces an immutable, content-addressed `Baseline`.
- Baselines are never edited. They are superseded, with a recorded reason.
- Every subsequent commit computes variance against every live baseline **synchronously, as part of the commit**. Not on a schedule, not at review time. A scope change that is discovered late is the failure this prevents.

### I8 — Constraint traceability

- Every `Constraint` — regulatory, contractual, policy — traces to at least one `Story`, or `ConstraintCritic` blocks G4.
- A `Constraint` may **never** rest on T4 inference. Every one carries its source document and a locator.
- A model-imagined regulatory obligation is a liability, not a requirement.

### I9 — Forensic posture (onboarding mode)

- Every reconstructed claim is stated as **what appears to have been decided, and what it rests on**. Never as a judgement of whether it was right.
- No artifact produced in onboarding mode evaluates a past decision or attributes fault to a person.
- `RedTeam` is **disabled** in onboarding mode. Its mandate is adversarial and it would happily generate a career-limiting sentence about the user's predecessor.
- Every reconstructed claim carries a band — safe to say / say with a caveat / ask, don't say — and the band is visible everywhere the claim appears.

---

## Two operational guardrails

### Tests run without an API key

The repository is public from the first commit. CI on a fork PR has no secrets.

- The default test suite must pass with **no LLM credentials present**.
- Agent tests use recorded responses committed as fixtures.
- Live-call tests sit behind an opt-in marker (`-m live`) and never run in default CI.
- A phase whose tests only pass with a key is not done.

### Secrets

- Configuration comes from environment variables; `.env` for local development, listed in `.gitignore`, with `.env.example` committed.
- No key, token or customer document ever enters git. Secret scanning runs as a pre-commit hook and in CI.
- Ingested source material lives in a run directory that is gitignored by default. Sample corpora committed to the repo must be synthetic or public-domain.

---

## Single source of record per field

| Field type | Primary source | Cross-check |
|---|---|---|
| Evidence span text | the `Source` file bytes at the recorded offsets | re-extract and compare at render time; mismatch fails |
| Claim tier and kind | classification at creation by `Ingestor` / `Elicitor` | `EvidenceAuditor` re-validates against the source kind |
| **Any numeric field** | the registered function in `probative.formulas` | `FormulaValidator` recomputes and diffs on every commit |
| Confidence | computed from basis + tier decay | never authored; a hand-set value is rejected |
| Constraint text | the obligation document, with locator | `ConstraintTracer`; T4 provenance forbidden |
| Satisfaction (brownfield) | the operational signal series | `IncumbentRater` renders the signal beside the score |
| Tracker key ↔ node id | the export ledger in the run directory | diff plan reconciles before any write |
| Baseline content | content-addressed snapshot hash | immutable; `SUPERSEDES` only |
| Phase status | `PHASES.md` | the gating check in the phase spec |

---

## Agents

- **Agents never mutate the graph.** They return an `AgentResult` containing a proposed patch. The `Committer` applies it only after validators and critics pass.
- Every agent has a typed input and output model. Malformed output is a caught error with a repair loop, not a garbled document.
- Every critic has a rubric file. Rubrics are data, not prose buried in a prompt — they are how a contributor adds a critic without touching the runtime.
- Critic severity is `block | warn | note`. A `block` genuinely stops the pipeline. If a critic cannot block, it is a linter, and it should be honest about that.

---

## Quality bar — phases requiring independent subagent review before "done"

A green test suite is not sufficient for these. Launch a subagent for a fresh read that was not anchored by the implementation:

- **PB10** graph core — the schema is the thing everyone else builds against
- **PB11** formula registry — I4 lives or dies here
- **PB5–PB8, PB22, PB39–PB40** every critic phase, plus the onboarding reconstruction and people map — I9 is a reputational guardrail for the user, not a style rule — a miscalibrated critic is worse than no critic
- **PB27** baselines and variance — silent drift is the failure mode
- **PB28** exporters — this writes into someone else's backlog

---

## Session invariants

- No code before plan approval.
- **One phase = one small PR.** When scope sprawls, stop and either slice the phase (`-p1`/`-p2`) or open a new row. Never quietly absorb the extra work.
- Do not build on an unconfirmed assumption. Probe the actual API, read the actual file, run the actual query, and record what you found. A documented shape that has never been verified is a rumour.
- When the spec and reality disagree, reality wins and the spec is corrected in the same session.
