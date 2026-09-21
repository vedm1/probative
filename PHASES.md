# PHASES.md — Probative Build Tracker

One row per phase. Flip 🔲 → ✅ when the phase is complete: all tests green, docs updated, PR merged.

Read this file with `grep`/`awk`, not whole — the Summary column becomes the project's real changelog and grows large.

| Phase | Name | Status | Summary |
|-------|------|--------|---------|
| **PB0** | Foundation | ✅ Done | `pyproject.toml` (hatchling, py3.12+), `src/probative/{core,agents,graph_runtime,render,exporters,interfaces,llm,formulas}` scaffolded. `probative.config.Settings` (pydantic-settings): loads with zero env vars; `credential_for(provider)` raises typed `MissingCredentialsError` instead of crashing. `probative.llm`: `Provider` protocol (`complete_structured`), `Message`/`TokenUsage`/`StructuredResult[T]`, `FakeProvider` for agent tests, `LiteLLMProvider` (lazy `import litellm`, injectable `completion_fn` for fixture replay) — the only module allowed to import litellm, enforced by an AST-walking test. `probative.cli`: typer app, `--version`/`--help` only. Tests: 15 in default suite (conftest autouse-scrubs `*_API_KEY`; `-m "not live"` default; 1 `live`-marked test excluded), 95% coverage. `uv sync`/`ruff check`/`ruff format --check`/`mypy src`/`pytest` all green with no credentials present. Pre-commit (ruff, gitleaks, large-file/EOF/whitespace) verified to actually reject a staged fake AWS key (exit 1). CI: `.github/workflows/ci.yml` (push + PR, py3.12/3.13 matrix, no secrets referenced) + `.github/workflows/release.yml` (PyPI Trusted Publishing on `v*` tag). Repo already existed on GitHub (`vedm1/probative`, Apache-2.0, README stub) — built on top of it rather than re-initializing. Domain: `probative.wevit.ai`. |
| **PB1** | Ingest: unstructured | 🔲 Planned | PDF, DOCX, XLSX, CSV, Markdown, TXT → `Source` + `EvidenceSpan` with stable, re-derivable offsets |
| **PB2** | Ingest: structured exports | 🔲 Planned | Confluence export, Jira CSV, ADO CSV → sources plus recognised issues, acceptance criteria and hierarchy |
| **PB3** | Finding model + critic framework | 🔲 Planned | `Finding`, severity, rubric file format and loader, critic base class, aggregation, dimension scoring |
| **PB4** | Shallow extraction | 🔲 Planned | Claims, needs, stories, constraints and dependencies extracted from a single document — no graph required |
| **PB5** | Critics: SpaceWarden, INVESTCritic | 🔲 Planned | Solution-shaped needs (I3) and story quality against the six INVEST properties |
| **PB6** | Critics: EvidenceAuditor, SegmentSkeptic | 🔲 Planned | Unsourced claims and authored numbers (I1, I4); segments that are demographic buckets |
| **PB7** | Critics: ConstraintCritic, DependencyCritic | 🔲 Planned | Untraced obligations (I8) and unowned cross-boundary dependencies |
| **PB8** | Critic: RedTeam | 🔲 Planned | Adversarial counter-case with rubric: named failure modes, what would have to be true |
| **PB9** | Critique report | 🔲 Planned | Scored dimensions plus qualitative findings with quoted evidence; Markdown and single-file HTML — **Slice C ships** |
| **PB33** | MCP server | 🔲 Planned | Expose `critique`, and later the run operations, as MCP tools |
| **PB34** | Claude Code / Cowork plugin skin | 🔲 Planned | Slash commands and skill over the MCP server; thin by construction |
| **PB10** | Graph core | 🔲 Planned | Node and edge types, `graph.json` schema, SQLite mirror, `partition`/`owner`, `SUPERSEDES`, I1 and I5 validators |
| **PB11** | Formula registry | 🔲 Planned | Every Olsen formula as a pure function, unit-tested against the book's worked examples; `FormulaValidator` (I4) |
| **PB12** | Runtime | 🔲 Planned | LangGraph phase machine, propose/dispose patches, `Committer`, critic fan-out, repair loop, gates with interrupt, checkpointing, budgets |
| **PB13** | Evidence ledger | 🔲 Planned | Tier and kind classification, dedupe, entity resolution, contradiction detection, corroboration, confidence propagation |
| **PB14** | Elicitor + BiasHunter | 🔲 Planned | Adaptive interrogation with basis capture and information-gain stopping; transcript audited for leading questions |
| **PB15** | DeskResearcher | 🔲 Planned | Web and MCP research → T2 with URL, retrieval timestamp and content hash |
| **PB16** | Segments + proto-personas | 🔲 Planned | Segment hypotheses, users vs buyers, adoption position; proto-persona projection → **G1** |
| **PB17** | Needs, ladders, hierarchy | 🔲 Planned | Olsen-form benefits, benefit ladders, `REQUIRES` edges between needs |
| **PB18** | Ratings, opportunity, Kano | 🔲 Planned | Importance and satisfaction with tier, n and dispersion; both opportunity formulas; Kano classification → **G2** |
| **PB19** | Opportunity landscape | 🔲 Planned | Interactive importance/satisfaction scatter with confidence envelopes and rectangle-area value rendering — **Slice A ships** |
| **PB20** | Brownfield: as-is model | 🔲 Planned | `ProcessMapper`, `ProcessModel`/`ProcessStep` from documentary and system evidence; mermaid render |
| **PB21** | Brownfield: incumbent satisfaction | 🔲 Planned | `IncumbentRater` from operational signals with confidence bands; `WorkaroundHunter` |
| **PB22** | Brownfield: constraints | 🔲 Planned | `ConstraintTracer`, obligation extraction with locators, constraint → story traceability, I8 enforcement |
| **PB23** | Value proposition | 🔲 Planned | Kano × alternatives, differentiators vs table stakes, the explicit refusal list → **G3** |
| **PB24** | Features → MVP | 🔲 Planned | Divergent ideation, chunking below the story-point threshold, estimates with uncertainty, ROI ranking, MVP selection |
| **PB25** | Dependencies + premortem | 🔲 Planned | `DependencyMapper`, unowned-dependency gate block, premortem ritual bound to hypotheses and constraints → **G4** |
| **PB26** | Story map + stories | 🔲 Planned | Backbone, walking skeleton, INVEST stories, acceptance criteria → **G5** |
| **PB27** | Baselines + variance | 🔲 Planned | I7: content-addressed snapshot at each gate, variance computed at commit, blast radius, severity |
| **PB28** | Exporters | 🔲 Planned | Jira and ADO CSV with real issue-type hierarchy, `probative-id` ledger, idempotent create/update/skip diff plan |
| **PB29** | Provenance story map | 🔲 Planned | Colour-coded interactive story map; click a card for the quote and the full derivation chain — the demo |
| **PB30** | RTM + RAID + assumption ledger | 🔲 Planned | Requirements traceability matrix, RAID log to XLSX, assumption ledger ranked by what breaks if false |
| **PB31** | Journey + empathy projections | 🔲 Planned | Journey stages and touchpoints, empathy entries with inference marking — *first cut candidate under schedule pressure* |
| **PB36** | Ingest: delivery artifacts | 🔲 Planned | Git history, PR review threads, Confluence page history and view counts, feature-flag config → `delivery` evidence kind |
| **PB37** | Code archaeology | 🔲 Planned | Business rules from test names, feature-flag state, DB migration timeline, dead code, API surface — the "safe to say" band |
| **PB38** | Ticket forensics | 🔲 Planned | Lifecycle stats, reopen counts, time-in-status, Won't-Fix and stale tickets as the recovered refusal list |
| **PB39** | Reconstruction + banding | 🔲 Planned | Product map, glossary, decision log; every claim banded safe-to-say / caveat / ask. `NeutralityCritic` (I9) |
| **PB40** | People and knowledge map | 🔲 Planned | Contributor graph per area, departed contributors, where knowledge has left the building. Never performance commentary |
| **PB41** | Onboarding pack + conversation prep | 🔲 Planned | Ranked question list with who-to-ask, contradiction and absence lists, `onboard brief --topic` — **`onboard` ships** |
| **PB35** | GitHub Action | 🔲 Planned | Critique runs on any PR touching a spec and posts findings as review comments — distribution vector for teams keeping specs in git |
| **PB32** | Eval harness | 🔲 Planned | Metrics runner, seeded-defect corpus, per-provider variance against a pinned reference model — **v0.1 complete** |

---

## Gate Dependencies

```
PB0 ─┬─► PB1 ─► PB2 ──────────────┐
     │                            │
     ├─► PB3 ─► PB4 ─┬─► PB5 ─┐   │
     │               ├─► PB6 ─┤   │
     │               ├─► PB7 ─┼───┴─► PB9 ─┬─► PB33 ─► PB34
     │                    └─► PB35
     │               └─► PB8 ─┘            │
     │                          [Slice C ships]
     │
     └─► PB10 ─┬─► PB36 ─► PB37 ─► PB38 ─► PB39 ─► PB40 ─► PB41
                │                              [onboard ships]
                └─► PB11 ─► PB12 ─┬─► PB13 ─┬─► PB14 ─► PB16 ─► PB17 ─► PB18 ─► PB19
                               │         │                                [Slice A ships]
                               │         └─► PB15 ─┘
                               │
                               └─► PB20 ─► PB21 ─► PB22

PB18 + PB22 ─► PB23 ─► PB24 ─► PB25 ─► PB26 ─┬─► PB27
                                             ├─► PB28
                                             └─► PB29 ─► PB30 ─► PB31

PB3 + PB19 ─► PB32
```

Three gates that matter more than the arrows suggest:

- **PB11 must be green before PB18.** The formula registry is what makes I4 real. Opportunity scoring built before it would bake in generated numbers, and every artifact downstream would inherit them.
- **PB10 must carry `partition` and `owner` before any node type is used in anger.** Retrofitting an ownership axis after PB26 means touching every node, every migration and every renderer. Two fields now; a rewrite later.
- **PB22 must gate PB25.** Constraints have to exist before the MVP gate that is supposed to block on untraced ones. Building G4 first and adding constraint checking afterwards means shipping a gate that silently passed everything.

**`onboard` (PB36–PB41) ships before the forward pipeline.** It needs the graph (PB10) but not the runtime or the scoring layer, and it has an even weaker cold-start requirement than `critique` — the artifacts already exist and nobody has to have written anything new. It also produces the as-is model the brownfield path otherwise assumes, so building it first means PB20 inherits a working input rather than a hypothetical one.

PB33, PB34 and PB35 sit after PB9 rather than at the end: the plugin skin is how most people will first run `critique`, and it is cheap once the CLI works.

---

## What "Complete" Means Per Phase

**PB0** — `uv sync` installs cleanly on a fresh machine. `uv run pytest` passes with zero LLM credentials in the environment. `uv run ruff check` and `uv run mypy src` are clean. CI runs all three on a pull request from a fork and passes. `LICENSE` (Apache-2.0), `CONTRIBUTING.md`, `SECURITY.md`, `.env.example` and secret-scanning pre-commit hooks exist. `probative --version` prints. The name has been confirmed unclaimed on pypi.org and GitHub, and the domain checked, before the first push.

**PB1** — Each supported format round-trips: ingest a file, recover an `EvidenceSpan`, re-extract from the source bytes at the recorded offsets, and get identical text. Offsets survive re-ingestion of the same file. A malformed or encrypted file fails with a clear error rather than silent partial extraction. Fixture corpus committed, synthetic or public-domain only.

**PB2** — A Jira CSV export, an ADO CSV export and a Confluence export each produce sources with recognised issue keys, hierarchy and acceptance criteria where present. Column-order variation across instances does not break parsing. Unknown columns are preserved, not dropped.

**PB3** — A critic can be added by writing a rubric file and a class with one method, with no runtime changes. Findings aggregate into dimension scores deterministically: the same findings always produce the same score. Severity ordering is enforced by type.

**PB4** — Extraction from a document produces typed candidates with locators back into the source. Precision and recall measured against a hand-labelled fixture and recorded in the phase spec. An extraction with no locator is rejected.

**PB5** — `SpaceWarden` catches every seeded solution-shaped need in the fixture set and raises nothing on the clean set. `INVESTCritic` scores each property independently with a stated reason. Both false-positive rates recorded.

**PB9** — `probative critique <file>` returns in under 60 seconds on a 30-page document, emits Markdown and single-file HTML, and every finding carries a quote with a locator. Runs against recorded fixtures in CI with no key.

Beyond PB9, the gating check lives in each phase's spec section rather than here.
