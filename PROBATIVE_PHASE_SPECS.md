# PROBATIVE_PHASE_SPECS.md — Detailed Phase Specifications

Specs are written just-in-time, at the start of a phase's build session. PB0 and PB1 are fully specified. Everything later carries objective, prerequisites and scope stubs — a detailed spec written months before the phase runs will be wrong by the time you reach it.

**Implementation notes** are appended *after* a build session and are the highest-value content in this file. They record what the spec got wrong and what reality turned out to be.

---

# Shared specifications

These are cross-phase and referenced rather than restated.

## S1 — The agent contract

Every agent implements:

```python
class Agent(Protocol):
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    tools: list[Tool]              # deterministic functions it may call
    tier_policy: TierPolicy        # what evidence it may rest on

    def run(self, state: GraphState, ctx: RunContext) -> AgentResult: ...


class AgentResult(BaseModel):
    proposed_nodes: list[Node]
    proposed_edges: list[Edge]
    tool_calls: list[ToolCall]     # audited; formula calls must appear here
    rationale: str
    self_assessment: SelfAssessment
    cost: CostRecord
```

**Agents never mutate the graph.** They return a patch. The `Committer` applies it only after deterministic validators and then critics pass. Rejected patches are retained under `runs/<id>/rejected/` with their findings attached.

`SelfAssessment` carries what the agent was least sure about, and is surfaced in the assumption ledger rather than discarded.

## S2 — Rubric file format

Critics are configured by data, not by prose buried in a prompt. A contributor adds a critic by writing a rubric and a class with one method.

```yaml
id: space_warden
severity: block
invariant: I3
applies_to: [Need, FeatureIdea]
checks:
  - id: solution_grammar
    description: A Need that names a feature, a UI element, or an implementation
    examples_bad: ["users need a dashboard", "provide an API for reconciliation"]
    examples_good: ["help me see where my money went this month"]
    remedy: Restate as a customer benefit — verb first, customer voice
clean_fixtures: fixtures/clean/needs_*.json    # must raise nothing on these
defect_fixtures: fixtures/seeded/space_*.json  # must catch every one
```

Every rubric names both a defect fixture set it must catch and a clean set on which it must raise nothing. **The false-positive requirement is not optional** — a critic that fires on clean input is worse than no critic.

## S3 — Testing without an API key

The repository is public; CI on a fork PR has no secrets. Consequences, binding from PB0:

- Default `pytest` run passes with **no LLM credentials in the environment**.
- Every agent test uses a recorded response fixture. Recording is a developer action, replay is the default.
- Live tests are marked `@pytest.mark.live` and excluded from default CI.
- Fixtures are committed. Any fixture derived from real customer material must be synthetic or public-domain — see `CLAUDE.md` § Secrets.
- A phase whose tests only pass with a key is not done.

## S4 — Artifact design system

Three phases render single-file HTML (PB19, PB29, PB9) and they must read as one system. No build step, no CDN, no external fonts — everything inline.

**Provenance scale.** The one visual language the whole product depends on. Chosen to survive both themes and the common forms of colour blindness; tier is *always* also carried by a text label and a pattern, never by hue alone.

| Tier | Role | Encoding |
|---|---|---|
| T1 Primary | strongest | solid fill, darkest weight |
| T2 Secondary | strong | solid fill, mid weight |
| T3 Elicited | provisional | hatched fill |
| T4 Inferred | derived | dotted outline, no fill |
| T5 Simulated | quarantined | ghost — reduced opacity, distinct channel, never the primary series |

**Rules.** Light and dark both defined as token sets on `:root`, never a colour defined only inside a media query. Every chart element reachable by keyboard. Every number rendered next to its confidence, never alone. Every clickable element opens the evidence drawer — if a thing cannot be traced, it is not clickable, and that absence is itself information.

## S5 — Reconstruction banding and posture (onboarding mode)

Cross-phase, used by PB39, PB40 and PB41. See `docs/DESIGN.md` §7.6.

**The three bands.** Every reconstructed claim carries exactly one, and it travels with the claim into every artifact:

| Band | May rest on | Rendering |
|---|---|---|
| `safe_to_say` | T1 `system` evidence — code running in production — or an explicit decision record with a locator | solid, darkest weight |
| `caveat` | T4 inference over T1 `delivery` evidence: tickets, PRs, commits, review threads | hatched |
| `ask` | T4 with thin, conflicting or single-source support | dotted outline |

Banding is computed, not authored — it derives from the claim's provenance, so it is a `formula_id` like any other numeric or categorical field (I4).

**Asymmetry rule.** When a claim is borderline between two bands, it goes to the *weaker* one. Over-banding costs the user a question; under-banding costs them their standing in a meeting. These are not equivalent errors and the implementation must not treat them as such.

**Posture — I9.** Enforced by `NeutralityCritic`:

- Claims are phrased as *what appears to have been decided, and what it rests on*. Never whether it was right.
- No claim attributes fault, competence or intent to a named person.
- `RedTeam` does not run in onboarding mode. This is a runtime exclusion in the mode config, not a prompt instruction.
- The people map states where knowledge is concentrated and where contributors have become inactive. It never characterises how anyone performed.

**Test the negative.** Each of PB39–PB41 ships with a fixture corpus containing a genuinely bad past decision. The assertion is that the output describes it neutrally and does not evaluate it. An implementation that produces a fair-but-critical assessment has failed the phase.

---

# PB0 — Foundation

**Objective**: A public, installable, CI-verified Python repository that does nothing yet and does it correctly.

**Prerequisites**: OI1 ✅ — the name is Probative. The residual availability check is part of this phase's gating check below, not a blocker on starting.

**In scope**

- `pyproject.toml`, `uv` lockfile, Python 3.12+, src layout: `src/probative/` with `core/`, `agents/`, `graph_runtime/`, `render/`, `exporters/`, `interfaces/`, `llm/`, `formulas/`.
- Tooling: `ruff` (lint + format), `pytest` with coverage, `mypy` strict on `src/probative/core` and `src/probative/formulas`, permissive elsewhere initially.
- `src/probative/llm/` — the provider adapter. Narrow internal interface: structured output against a Pydantic model, plus token accounting. LiteLLM is an implementation detail behind it.
- Configuration: environment variables, `.env` for local dev (gitignored), `.env.example` committed.
- CLI entry point: `probative --version`, `probative --help`. Nothing else.
- CI: GitHub Actions running `ruff check`, `mypy src`, `pytest` on push and on pull requests **from forks**, with no secrets available.
- Repository furniture: `LICENSE` (Apache-2.0), `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.gitignore`, `docs/DESIGN.md`.
- Pre-commit: ruff, secret scanning, large-file check.

**Out of scope for PB0**: any graph type, any agent, any formula, any parsing. Phase 0 is foundation and nothing else. If it is tempting to add "just the node types while we're here", that temptation is PB10.

**Tests**

- `test_version` — `probative --version` returns the packaged version.
- `test_no_llm_import_leak` — asserts no module outside `src/probative/llm/` imports `litellm`. This test is the PB0 risk mitigation and it must exist from the first commit.
- `test_config_loads_without_env` — configuration loads with no environment variables set and reports missing credentials as a typed error, not a crash.
- Smoke test asserting the package imports cleanly.

**Gating check**

```bash
uv sync            # clean install on a fresh machine
uv run ruff check  # clean
uv run mypy src    # passes
uv run pytest      # passes with no LLM credentials in the environment
```

CI runs all four on a pull request from a fork and passes. Secret-scanning pre-commit hook rejects a test commit containing a fake key.

**Name verification — do this before the first `git push`, not after:** confirm `probative` is unclaimed on pypi.org directly (the JSON API blocks automated fetching, so check in a browser), search GitHub for an existing `probative` project in the AI-tooling space, and check the domain. If any of these is taken, stop and re-decide — this is the last cheap moment. Fallbacks already vetted and clear on search: `proofmark`, `trigpoint`, `toulmin`.

**Implementation notes (resolved during build session)**:

- **Name verification, resolved 2026-09-21.** PyPI: free (`/simple/probative/` → 404; the project page itself is behind a bot-challenge and not usable as the check). GitHub: two unrelated `probative` repos exist, both created 2026-08-28/29, both ★0, both untouched since — `Vojtaupan/probative` is a same-space AI-tooling side project ("checks whether the tool-call record backs up what your agent said") but has no traction. Domains `probative.io`/`.ai` are taken by others; **the project's own domain is `probative.wevit.ai`** (parented under wevit.ai per `docs/DESIGN.md` R7). Decision: proceed with `probative`, register a PyPI pending publisher immediately, and cut a `0.1.0.dev0` tag as soon as this PR merges — that's the moment the name is actually locked, not the decision to use it.
- **The GitHub repo `vedm1/probative` already existed** (Apache-2.0 `LICENSE`, a stub `README.md`, a `.gitignore`) with one commit before this session started. PB0 built on top of that commit (`git init` locally, added it as `origin`, checked out `main`) rather than re-initializing — the upstream `LICENSE` and `.gitignore` (the GitHub Python template) were kept and only extended, not replaced.
- **PyPI trusted publishing, not an API token.** `release.yml` publishes via OIDC (`pypa/gh-action-pypi-publish` + `id-token: write`) on a `v*` tag. Registering the pending publisher on pypi.org (owner `vedm1`, repo `probative`, workflow `release.yml`, environment `pypi`) is a manual step only the account owner can do — it's not automatable from this session and isn't done yet.
- **`no_args_is_help=True` exits 2, not 0.** The spec's test list implies a clean `--help` path; Click's actual behaviour for a bare invocation under `no_args_is_help` is a usage-error exit (2) with help text on stdout, not exit 0. `test_no_args_shows_help` asserts 2 — verified against the installed Typer/Click version rather than assumed.
- **`no-any-return` under mypy strict bit twice** in code that looked innocuous: `getattr(self, field_name)` in `Settings.credential_for` and `return litellm.completion` in `LiteLLMProvider._completion` (litellm has no type stubs, so `ignore_missing_imports = true` makes every attribute on it `Any`). Fixed by replacing the `getattr` indirection with an explicit `dict[str, SecretStr | None]` literal, and an explicit `cast(CompletionFn, litellm.completion)` at the one deliberate boundary where an untyped SDK meets typed code.
- **`ruff format` walks Markdown fenced Python blocks by default** in this ruff version, and would have reformatted the illustrative `AgentResult`/`Agent` snippets in `docs/DESIGN.md` and this very file (S1). Excluded `docs/` and `*.md` from ruff's scope (`extend-exclude` in `pyproject.toml`) — those files are prose owned by the planning process, not source PB0 should be rewriting. The same reasoning was applied to the `trailing-whitespace`/`end-of-file-fixer` pre-commit hooks, scoped away from `docs/` and the root `CLAUDE.md`/`PHASES.md`/`PROBATIVE_*.md` files so a future build session's `pre-commit run --all-files` can't silently carry a whitespace diff into a doc it wasn't asked to touch.
- **The secret-scanning gating check needed a non-placeholder fake key to prove anything.** A first attempt using AWS's own documented example key (`AKIAIOSFODNN7EXAMPLE`) passed gitleaks silently — it's a well-known placeholder gitleaks' default ruleset (implicitly, via entropy/allowlist behaviour) doesn't flag. A randomly generated key in the same `AKIA[16 chars]` shape was correctly caught (`aws-access-token` rule, hook exits 1). Recorded here because the spec's own gating check ("commit a test key, watch the hook reject it") is easy to satisfy with a false negative if the test key is a recognisable textbook example.
- **`uv sync` (no flags) already installs the `dev` dependency-group** — `uv` treats `dev` as a default group, so the gating check's literal `uv sync` command (not `uv sync --all-groups`) is sufficient to get `ruff`/`mypy`/`pytest` on PATH via `uv run`. Confirmed rather than assumed, since the spec's four-line gating block would otherwise be unrunnable as written.
- **`Settings.model` reads from the `MODEL` env var**, case-insensitively (pydantic-settings default) — documented in `.env.example` as `MODEL=`, not `PROBATIVE_MODEL=`; no `env_prefix` was set, since there's only one provider-agnostic settings object in the project so far and a prefix would just add noise. Revisit if a second `BaseSettings` subclass appears.

---

# PB1 — Ingest: unstructured documents

**Objective**: Turn a folder of ordinary documents into `Source` and `EvidenceSpan` records whose offsets survive re-extraction, so that every downstream provenance claim can be verified rather than trusted.

**Prerequisites**: PB0 ✅. OI4 (dogfood corpus) helpful but not blocking — a synthetic fixture set is sufficient to build against.

**In scope**

- Formats: PDF (text-layer), DOCX, XLSX, CSV, Markdown, plain text.
- `Source` — id, path, sha256 of the bytes, format, ingested-at, declared `tier` and `kind` (see `docs/DESIGN.md` §5.1), extractor and extractor version.
- `EvidenceSpan` — source id, character offsets into a **normalised text projection** of the source, the extracted text, and a locator meaningful to a human (page and line for PDF, sheet and cell for XLSX, heading path for Markdown).
- A stable normalisation step per format, versioned, so that the same file always produces the same projection. The extractor version is recorded on the source because a change to normalisation invalidates existing offsets and must be detectable.
- OCR is **detected and refused** at PB1 with a clear message naming the file. Scanned documents are PB1-ext, not a silent partial extraction.
- Encrypted or corrupt files fail loudly, naming the file and the reason.

**Out of scope for PB1**: Confluence and tracker exports (PB2); images (later); tier and kind *inference* — at PB1 they are declared by the caller, not guessed; any claim extraction (PB4).

**Contracts**

```python
def ingest(path: Path, *, tier: Tier, kind: EvidenceKind) -> Source
def spans(source: Source, ranges: list[Range]) -> list[EvidenceSpan]
def reextract(span: EvidenceSpan) -> str   # must equal span.text, always
```

**Tests**

- **Round-trip, per format**: ingest a fixture, take spans at known ranges, call `reextract`, assert byte-identical text. This is the phase's reason to exist.
- **Idempotence**: ingesting the same file twice produces identical source hash and identical offsets.
- **Normalisation stability**: a golden test pinning the normalised projection of each fixture, so a change to normalisation fails loudly rather than silently invalidating spans.
- **Locator correctness**: a span in a known PDF reports the correct page; a span in a known XLSX reports the correct sheet and cell.
- **Failure modes**: encrypted PDF, zero-byte file, XLSX with the header row not first, CSV with inconsistent column counts, a PDF with no text layer — each raises a typed error naming the file.

**Gating check**: `uv run pytest tests/ingest -q` green, including the round-trip test across all six formats, on a committed fixture corpus that is synthetic or public-domain.

**Implementation notes (resolved during build session)**: *(to be appended)*

---

# Later phases — stubs

Specs are written at the start of each build session. These record objective, prerequisites and known unknowns only.

## PB2 — Ingest: structured exports
**Objective**: Confluence exports and Jira/ADO CSV exports become sources with recognised issue keys, hierarchy and acceptance criteria.
**Prerequisites**: PB1 ✅, OI5 resolved.
**Known unknowns**: how many Confluence export variants matter; whether ADO's HTML description field needs its own normalisation path.

## PB3 — Finding model + critic framework
**Objective**: A critic can be added by writing a rubric file (S2) and a class with one method, with no runtime change.
**Prerequisites**: PB0 ✅, OI3 resolved.
**Known unknowns**: whether dimension scores should be a weighted mean of findings or a floor-based rubric; the former is smoother, the latter harder to game.

## PB4 — Shallow extraction
**Objective**: Typed candidates — claims, needs, stories, constraints, dependencies — extracted from a single document with locators, without constructing a graph.
**Prerequisites**: PB1, PB2, PB3 ✅.
**Known unknowns**: precision/recall achievable on unstructured PRDs; whether constraint extraction needs its own pass.

## PB5 — Critics: SpaceWarden, INVESTCritic
**Prerequisites**: PB4 ✅, OI2 and OI3 resolved. Subagent review required.

## PB6 — Critics: EvidenceAuditor, SegmentSkeptic
**Prerequisites**: PB4 ✅. Subagent review required.

## PB7 — Critics: ConstraintCritic, DependencyCritic
**Prerequisites**: PB4 ✅. Subagent review required.
**Note**: in standalone critique mode these report untraced obligations and unowned dependencies found *within the document*. Graph-wide enforcement is PB22 and PB25.

## PB8 — Critic: RedTeam
**Prerequisites**: PB4 ✅. Subagent review required.
**Known unknowns**: whether a generative critic can be held to a false-positive standard the same way a rule-checkable one can.

## PB9 — Critique report
**Objective**: `probative critique <file>` → scored dimensions plus qualitative findings with quoted evidence, as Markdown and single-file HTML. **Slice C ships.**
**Prerequisites**: PB5–PB8 ✅, S4.

## PB33 — MCP server
**Objective**: Expose `critique` as an MCP tool; extend to run operations as later phases land.
**Prerequisites**: PB9 ✅.

## PB34 — Plugin skin
**Objective**: Slash commands and a skill over the MCP server. Thin by construction — no logic that is not in the core.
**Prerequisites**: PB33 ✅.

## PB36 — Ingest: delivery artifacts
**Objective**: Git history, PR review threads, Confluence page history and view counts, and feature-flag configuration become `Source` and `EvidenceSpan` records under a new `delivery` evidence kind.
**Prerequisites**: PB1, PB2, PB10 ✅. OI14 resolved (live connectors vs exports).
**Known unknowns**: whether v0.1 reads live connectors or exports only — a week-one joiner usually has neither access nor patience; how to represent a PR review thread as spans without losing who said what to whom.

## PB37 — Code archaeology
**Objective**: Extract business rules from test names, feature-flag state, DB migration timeline, dead code and API surface. This is the entire `safe_to_say` band — nothing else earns it.
**Prerequisites**: PB36 ✅, S5.
**Known unknowns**: test-name parsing is language- and framework-specific; pick one stack for v0.1 and say which. A rule extracted from a skipped or quarantined test is not a rule — detect that.

## PB38 — Ticket forensics
**Objective**: Lifecycle statistics, reopen counts, time-in-status, and Won't-Fix and stale tickets as the recovered refusal list.
**Prerequisites**: PB36 ✅. OI13 resolved (sampling strategy).
**Known unknowns**: four years of Jira exceeds any sensible budget. Ranking signals — recency, reopen count, link density, comment volume, Won't-Fix — need weights and a cap. Status names vary per project; the workflow itself has to be inferred before time-in-status means anything.

## PB39 — Reconstruction and banding
**Objective**: Product map, glossary with first appearance and who introduced each term, decision log, contradiction list, absence list. Every claim banded per S5. `NeutralityCritic` implements I9.
**Prerequisites**: PB37, PB38 ✅, S5. **Subagent review required.**
**Known unknowns**: absence detection needs a notion of what *should* be present — probably a small taxonomy of categories (accessibility, security, performance, a user type with no tickets) rather than open-ended inference.

## PB40 — People and knowledge map
**Objective**: Contributor graph per area from commits, reviews, comments and doc edits; inactive contributors marked; concentration of knowledge surfaced.
**Prerequisites**: PB36 ✅, S5. **Subagent review required.**
**Known unknowns**: identity resolution across git, Jira and Confluence is genuinely hard — one person is three accounts and two spellings. Where identities cannot be resolved confidently, aggregate rather than guess.
**Non-negotiable**: this phase describes where knowledge lives. It never characterises performance. See S5.

## PB41 — Onboarding pack and conversation prep
**Objective**: The ranked question list with who-to-ask, the HTML pack, and `probative onboard brief --topic X`. **`onboard` ships.**
**Prerequisites**: PB39, PB40 ✅, S4, S5.
**Known unknowns**: how to rank questions by how much each unblocks — probably blast radius over the reconstruction graph, the same computation as `blast_radius`. Cap the list; a new PM arriving with forty generated questions will annoy everyone and use the tool once.

## PB35 — GitHub Action
**Objective**: Critique runs on any PR touching a spec and posts findings as review comments.
**Prerequisites**: PB9 ✅.

## PB10 — Graph core
**Objective**: Node and edge types, `graph.json` schema, SQLite mirror, `partition`/`owner` on every node, `SUPERSEDES`, I1 and I5 validators.
**Prerequisites**: PB0 ✅, OI11 considered. Subagent review required.
**Known unknowns**: whether the SQLite mirror should be generated from the schema or hand-written.

## PB11 — Formula registry
**Objective**: Every Olsen formula as a registered pure function, unit-tested against the book's worked examples. `FormulaValidator` (I4) recomputes and diffs on commit.
**Prerequisites**: PB10 ✅. Subagent review required.
**Note**: worked examples to test against — Ulwick opportunity 10/5→15 and 6/1→11 (p. 57); customer value 0.7×0.7=0.49 (p. 60); opportunity 0.7×0.3=0.21 and 0.9×0.7=0.63 (p. 61); Feature X 0.82×0.45=0.37 (p. 62); value created 0.7×0.2=0.14 (p. 63); ROI 6÷2=3 vs 6÷4=1.5 (p. 82).

## PB12 — Runtime
**Objective**: LangGraph phase machine, propose/dispose patches, `Committer`, critic fan-out and join, repair loop capped at 3 cycles, gates with `interrupt_before`, SQLite checkpointing, per-phase token and wall-clock budgets, `TediumAuditor` interaction counters.
**Prerequisites**: PB10, PB11 ✅.

## PB13 — Evidence ledger
**Objective**: Tier and kind classification, dedupe, entity resolution, contradiction detection producing `CONTRADICTS` edges and `Question` nodes, corroboration by independent source, confidence propagation.
**Prerequisites**: PB12 ✅, OI4 resolved.

## PB14 — Elicitor + BiasHunter
**Objective**: Adaptive interrogation with basis capture, information-gain stopping, `unknown` as a valid outcome, in-the-moment challenge against ingested evidence. `BiasHunter` audits the transcript in the same phase.
**Prerequisites**: PB13 ✅.
**Known unknowns**: how to measure marginal information gain cheaply enough to run between questions.

## PB15 — DeskResearcher
**Prerequisites**: PB13 ✅.

## PB16 — Segments + proto-personas → G1
**Prerequisites**: PB14 ✅.

## PB17 — Needs, ladders, hierarchy
**Prerequisites**: PB16 ✅.

## PB18 — Ratings, opportunity, Kano → G2
**Prerequisites**: PB17, PB11 ✅.

## PB19 — Opportunity landscape
**Objective**: Interactive scatter, confidence envelopes sized by n and tier, rectangle-area value rendering, quadrant labels, T5 ghosts. **Slice A ships.**
**Prerequisites**: PB18 ✅, S4.

## PB20 — Brownfield: as-is model
**Prerequisites**: PB13 ✅, OI7 resolved.

## PB21 — Brownfield: incumbent satisfaction
**Prerequisites**: PB20 ✅.
**Known unknowns**: the mapping from operational signal to satisfaction is a registered formula with a stated rationale — which signals, and with what defensible transform, is the open question.

## PB22 — Brownfield: constraints
**Prerequisites**: PB20 ✅. Subagent review required.

## PB23 — Value proposition → G3
**Prerequisites**: PB18, PB22 ✅.

## PB24 — Features → MVP
**Prerequisites**: PB23 ✅, OI8 resolved.

## PB25 — Dependencies + premortem → G4
**Prerequisites**: PB24, PB22 ✅.

## PB26 — Story map + stories → G5
**Prerequisites**: PB25 ✅.

## PB27 — Baselines + variance
**Prerequisites**: PB26 ✅. Subagent review required.

## PB28 — Exporters
**Prerequisites**: PB26 ✅, OI6 resolved. Subagent review required.

## PB29 — Provenance story map
**Prerequisites**: PB26 ✅, S4, OI10 resolved.

## PB30 — RTM + RAID + assumption ledger
**Prerequisites**: PB27, PB29 ✅, OI9 resolved.

## PB31 — Journey + empathy projections
**Prerequisites**: PB17 ✅. *First cut candidate under schedule pressure.*

## PB32 — Eval harness
**Objective**: Metrics runner, seeded-defect corpus, per-provider variance against a pinned reference model. **v0.1 complete.**
**Prerequisites**: PB3, PB19 ✅, OI2 resolved.
