# Probative — Design & Architecture Spec

> **Name.** `probative` (adj.): having the quality of proving or demonstrating; in law, the degree to which a piece of evidence actually tends to prove a fact.
> **Status:** draft v0.3 · design phase · not yet implemented
> **Method source:** Dan Olsen, *The Lean Product Playbook* (Wiley, 2015). Page citations refer to the print edition.
>
> **v0.2 → v0.3:** brownfield transformation promoted to a first-class path (§7); BA-native artifacts in scope (§14); federated ownership and semantic merge (§12); operator corrected to PM/BA with beneficiaries (§1.1); v0.1 scope re-cut (§18).

---

## 1. What this is

An evidence-grounded, multi-agent product system. You give it seed material — documents, images, transcripts, spreadsheets, process docs, tracker exports, plain text — and it walks the Lean Product Process end to end: target customer, underserved needs, value proposition, MVP feature set, story map. It then holds that plan as a **baseline** and tells you, at the moment it happens, when reality diverges from it.

Three properties distinguish it.

1. **Every claim is traceable or typed as a hypothesis.** There is no third category. Artifacts violating this do not get produced — a validator rejects them before they are written.
2. **It is not tedious.** A design constraint with a measured budget, not an aspiration (I6, §8.5 → §9.5).
3. **It works brownfield.** Most product work in large organisations is modernising something that already exists, where the incumbent alternative is the client's own system. That path is first-class, not an afterthought (§7).

### 1.1 Audience

**Anyone accountable for what an SDLC team builds.** Generic by construction: everything derives from method (§19), never from any one team's situation.

**Role — operators and beneficiaries.**

| | Role | What they do with it |
|---|---|---|
| **Operator** | **Product manager / business analyst** | Drives runs. All defaults, ergonomics and vocabulary are tuned for this person. Founders and discovery consultants are operators wearing the same hat |
| Beneficiary | Engineer / tech lead | Receives stories carrying provenance, and a phase plan naming its dependencies |
| Beneficiary | Engineering manager | Receives dependency roll-ups, baselines, variance alerts |
| Beneficiary | Designer, QA | Receives journeys, process models, acceptance criteria bound to evidence |
| Beneficiary | Executive, delivery lead, audit | Receives the assumption ledger, refusal list, RTM, RAID, post-mortem |

Beneficiaries consume artifacts. They never drive the tool and are never required to keep anything updated. **A feature that demands work from a beneficiary is an I6 violation dressed up as collaboration.**

**Organisation size — handled by modes (§9.6).** Solo → team → enterprise transformation programme. What changes is ceremony, governance, evidence volume and the number of operators. Never the maths.

**Multiple operators are the norm at scale.** A 200-person programme has several PMs and BAs, each owning a scope area, working independently most of the time and colliding at the boundaries. That is not solved by modes and it is not fine-grained co-editing either — it is federated ownership with cross-boundary reconciliation, and it gets its own architecture (§12).

**Defaults are tuned for the solo case.** A tuning decision, not an audience restriction: a tool that stays pleasant with one person and no data will survive contact with forty stakeholders. The reverse has never once been true.

---

## 2. Positioning

### 2.1 Where this sits

The spec-driven development ecosystem — BMAD, GitHub Spec Kit, OpenSpec, Kiro — begins at *"here is my idea, write me a spec."* Every one assumes the problem is already understood. Olsen's entire book is upstream of that line.

Probative occupies the upstream, then follows the thread downstream far enough to know whether the plan survived.

```
seed material ──► PROBATIVE ────────────────────────────────────────────┐
 docs · transcripts │                                               │
 process models     ├─► validated problem space + story map         │
 ops data · tickets │        │                                      │
 tracker exports    │        ├─► Jira / ADO / Linear                │
                    │        ├─► RTM · RAID · as-is/to-be           │
                    │        └─► phase plan ──► spec-driven tools ──┤
                    │                              (build)          │
                    └─◄─── delivery signals ────────────────────────┘
                              │
                              ▼
                    baseline variance · scope alerts · post-mortem
```

### 2.2 Non-goals

- **Not a project tracker.** It exports into yours, reads status back, and gets out of the way.
- **Not a build tool.** It hands over a phase plan. It does not write code.
- **Not a real-time collaboration surface.** Federation is partition-and-merge (§12), not co-editing. No server, no accounts, no live cursors.
- **Not methodology-agnostic.** Olsen's process, opinionatedly. Alternatives may arrive later as additional scorers over the same graph.
- **Not a writing assistant.**

### 2.3 The eight failure modes it exists to prevent

**In discovery:**

1. **Invented personas.** An LLM-generated persona with a fabricated day-in-the-life is astrology. Proto-personas until real evidence exists, labelled as such everywhere.
2. **Confident numbers.** Asserted importance and satisfaction scores are worse than none, because they survive into decks. Numbers are computed by registered pure functions or they do not exist.
3. **Solutions wearing needs' clothing.** "Users need a dashboard" is not a need. Olsen Ch. 2 as an enforced type boundary with a critic that has veto power.
4. **Untraceable derivation.** Change a segment on day 40 and nobody knows which of the 90 stories just lost their justification.

**At the discovery/delivery seam:**

5. **Plan and product diverge invisibly.** Nothing reconciles what shipped against what was planned; no pre-mortem, no post-mortem, nothing learned. → **Baselines and the variance ledger** (§10).
6. **Scope changes surface too late to act on.** Lateness, not the change, is the failure. → **Variance emitted at commit time with blast radius** (§10.4).
7. **Cross-dependencies stay unresolved.** Visible from the start, owned by nobody, rediscovered at integration and again at launch. → **Dependency as a first-class node, blocking at the MVP gate** (§11).
8. **Parallel workstreams collide at integration.** Two BAs claim the same scope, or one's rating change quietly invalidates another's MVP selection. Discovered at integration, when it is expensive. → **Semantic merge and cross-partition variance** (§12).

---

## 3. What "real functional agent" means here

An agent in Probative is real because it has:

1. **A typed input and output contract** — Pydantic models validated on both sides. Malformed output is a caught error with a repair loop, not a garbled document.
2. **Deterministic tools it is required to use** — it cannot compute an opportunity score in its head; it must call `ulwick_opportunity`.
3. **The ability to fail and to block** — a critic returning `severity: block` stops the pipeline. Real control flow, not a suggestion in a prompt.
4. **No write access to state** — agents propose patches; a committer applies them only after validation.

### 3.1 The propose/dispose split

```python
class AgentResult(BaseModel):
    proposed_nodes: list[Node]
    proposed_edges: list[Edge]
    tool_calls: list[ToolCall]       # audited; formulas must appear here
    rationale: str
    self_assessment: SelfAssessment  # what it was least sure about
    cost: CostRecord
```

Agents never mutate the graph. They emit a **patch**, which runs a gauntlet — deterministic validators, then critics — and the `Committer` applies it only if it survives. Rejected patches are retained with their findings.

This gives critics genuine authority rather than advisory status, produces a complete audit trail of what was considered and discarded, and means a bad agent produces a *rejection* rather than a corrupted document.

---

## 4. Design invariants

Enforced mechanically. Each maps to a validator that can fail a run.

| # | Invariant | Enforced by |
|---|---|---|
| **I1** | No orphan claims. Every `Claim` carries ≥1 evidence edge, or is typed `Hypothesis`. | `EvidenceAuditor` (blocking) |
| **I2** | Every hypothesis is falsifiable — method, cost, duration, and a kill criterion stated before the test runs. | `Falsifier` (blocking) |
| **I3** | Problem space and solution space are separately typed and never silently mixed. | `SpaceWarden` (blocking) |
| **I4** | Numbers are computed, never generated. Every numeric field declares a `formula_id`; the validator recomputes and diffs. An LLM proposes *inputs*, never *outputs*. | `FormulaValidator` (deterministic, blocking) |
| **I5** | Every artifact is a projection. No artifact contains content absent from the graph. | Renderer has no free-text slots |
| **I6** | **Tedium budget.** Every human interaction is a decision, never transcription. Phases have hard interaction budgets. | `TediumAuditor`, measured per release (§9.5, §17) |
| **I7** | **Baseline integrity.** A committed gate produces an immutable snapshot; every later change computes variance against it at commit time. | `VarianceMonitor` (deterministic, blocking on silent drift) |
| **I9** | **Forensic posture.** In onboarding mode every reconstructed claim states what appears to have been decided and what it rests on, never whether it was right. No artifact evaluates a past decision or attributes fault to a person. | `NeutralityCritic` (blocking); `RedTeam` disabled in this mode |
| **I8** | **Constraint traceability.** Every `Constraint` — regulatory, contractual, policy — traces to at least one story, or the gap is raised. | `ConstraintCritic` (blocking at G4) |

**I4, I6 and I8 decide whether this is worth building.** I4 makes the output trustworthy, I6 makes anyone still be using it in month three, I8 is the difference between a nice tool and one a regulated programme can adopt.

---

## 5. The evidence model

### 5.1 Two orthogonal axes

Evidence is classified on **tier** (how direct) and **kind** (what sort of thing it is). Greenfield discovery leans on customer evidence; brownfield transformation leans on operational and documentary evidence. Both are legitimate; they are not the same and must not be conflated.

**Tier — how direct:**

| Tier | Name | What it is | Provenance requirement |
|---|---|---|---|
| **T1** | Primary | Direct observation of the real world: transcripts, tickets, reviews, survey responses, session recordings, production analytics, incident logs | Source id + span + attribution |
| **T2** | Secondary | Desk research retrieved by agents: analyst reports, competitor docs, forum threads, regulatory text | URL + retrieval timestamp + content hash |
| **T3** | Elicited | The operator's or a stakeholder's domain knowledge, extracted by structured interrogation | Question id + verbatim answer + declared basis and confidence |
| **T4** | Inferred | Model synthesis over T1–T3 | Declared parent node ids; never a leaf |
| **T5** | Simulated | Model-generated proxy responses | Quarantined (§5.5) |

**Kind — what sort of thing:**

| Kind | Examples | Typical use |
|---|---|---|
| `customer` | interviews, reviews, support tickets, NPS verbatims | needs, importance |
| `operational` | cycle times, error rates, ticket volumes, workaround prevalence, defect logs | **satisfaction with the incumbent**, current-state pain |
| `documentary` | SOPs, process maps, BRDs, contracts, audit findings | as-is process, constraints |
| `system` | schemas, API surfaces, config, legacy behaviour | as-is capability, dependencies |
| `delivery` | tickets, PRs, commit history, review threads, releases, feature flags | what the team *did* and appears to have intended — the raw material of onboarding mode |
| `market` | analyst reports, competitor teardowns, pricing | alternatives, satisfaction ceiling |

**Why the kind axis earns its place.** In a brownfield programme, satisfaction with the incumbent is measurable from operational data — cycle time, rework rate, how many people keep a shadow spreadsheet. That is T1 evidence, abundant, and considerably better than the survey a greenfield team wishes it had. Without the kind axis you either mislabel it as customer voice or throw it away.

### 5.2 T3 is not a consolation prize

Olsen is explicit that the framework can be used *"before you talk to a single customer… with a sample size of zero"* (p. 55), precisely because doing so forces hypotheses into the open where they can be tested. Elicitation is that mechanism made systematic. A practitioner's structured judgement, labelled as judgement, is legitimate input. The failure is not using it — the failure is laundering it into something that looks like customer data.

### 5.3 Confidence

Every `Claim` carries `confidence ∈ [0,1]` and `basis: [evidence_id]`.

- **Corroboration raises it**, but only from *independent* sources. Three quotes from one transcript count once.
- **Derivation caps it:** `derived.confidence ≤ min(parent.confidence) × tier_decay`.
- **Contradiction is preserved, never averaged.** Disagreeing spans produce a `CONTRADICTS` edge and an open `Question`. Averaging destroys what is often the most valuable signal in the corpus.

### 5.4 The tier policy

| Artifact element | T1 | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|
| Segment exists | ✅ | ✅ | ⚠️ hypothesis | ⚠️ | ❌ |
| Named "Persona" | ✅ requires ≥1 T1 `customer` | ❌ | ❌ | ❌ | ❌ |
| Named "Proto-persona" | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| Need exists | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| Importance rating | ✅ | ⚠️ | ⚠️ estimated | ❌ | ❌ |
| Satisfaction rating | ✅ | ✅ | ⚠️ estimated | ❌ | ❌ |
| Kano classification | ✅ | ⚠️ | ⚠️ | ❌ | ❌ |
| Constraint | ✅ | ✅ documentary only | ⚠️ must be confirmed | ❌ | ❌ |
| Value proposition | ✅ | ✅ | ✅ must list dependent assumptions | ✅ | ❌ |
| Story exported to tracker | ✅ | ✅ | ⚠️ amber flag | ⚠️ | ❌ blocked |

✅ permitted · ⚠️ permitted with a visible stamp and a required test · ❌ rejected

A `Constraint` may never rest on inference. A regulatory obligation the model believes exists is a liability, not a requirement.

### 5.5 Simulated respondents (T5) — resolved: quarantined

Permitted, structurally separated: never averaged into T1–T3 aggregates; rendered as ghost points on a distinct channel; excluded from gate satisfaction; watermarked in every export; stripped from tracker exports; the run header always states the split (`real: 3 rated · simulated: 14`). **`blend` is not implemented and will not be** — a quarantine a config flag can lift is not a quarantine, because then every downstream reader must ask whether it was lifted.

Its one sound use is as a pre-mortem instrument: if simulation scores a need at 0.6 and your instinct says 0.2, that disagreement is information about your instinct, generated for free.

---

## 6. The evidence graph

Everything is one typed graph. Personas, journey maps, empathy maps, process models, story maps, the RTM and the RAID log are **projections** over it, not documents.

### 6.1 Node types

```
── evidence ───────────────────────────────────────────────
Source              raw ingested artifact; carries tier + kind
EvidenceSpan        a located extract — the atom of provenance
Claim               an assertion, with tier + confidence + basis
Question            an open question, incl. contradictions awaiting resolution

── current state (brownfield) ─────────────────────────────
IncumbentSystem     the thing being replaced or modernised
ProcessModel        an as-is or to-be process
ProcessStep         a step within one, with actor, system, pain, metrics
Constraint          regulatory, contractual or policy obligation — non-negotiable
Workaround          observed shadow process; strong evidence of unmet need

── problem space (Olsen 1–2) ──────────────────────────────
Segment             target customer segment (Ch. 3)
Persona             projection over Segment + T1 customer evidence
Adoption            technology adoption lifecycle position (p. 29)
Need                a customer benefit, Olsen-form: verb-first, customer voice (Ch. 4)
Ladder              benefit ladder rung relationship (p. 41)
NeedHierarchy       conditional dependency between needs (p. 43)
Rating              Importance or Satisfaction, with tier, kind, n, dispersion
Opportunity         computed — never authored
KanoClass           must-have | performance | delighter | indifferent | reverse
Alternative         a competitor, or the IncumbentSystem itself
JourneyStage        ordered stage in a journey
Touchpoint          interaction within a stage
EmpathyEntry        says | thinks | does | feels — each evidence-bound

── solution space (Olsen 3–5, Patton) ─────────────────────
ValueProp           needs addressed, and needs deliberately refused (Ch. 5)
FeatureIdea         divergent solution idea, bound to a Need (Ch. 6)
FeatureChunk        broken below the story-point threshold (p. 79)
Estimate            effort with explicit uncertainty
MVPMembership       computed — in the v1 column or not (p. 85)
Backbone            story map backbone activity (Patton)
Story               INVEST-conformant user story (p. 78)
AcceptanceCriterion

── continuity ─────────────────────────────────────────────
Dependency          cross-boundary: team, system, vendor, data, legal, migration
Baseline            immutable snapshot at a gate commit
Variance            computed divergence from a Baseline
BuildPhase          a unit of the downstream build plan
DeliverySignal      status read back from tracker or build tooling
Premortem           pre-commit failure analysis, recorded before work starts
Postmortem          reconciliation of Baseline against DeliverySignal

── process ────────────────────────────────────────────────
Hypothesis · Test · Decision · Finding · Risk
```

**Every node carries `partition` and `owner`.** Even in single-operator runs, where both default to `main` and the operator. Retrofitting an ownership axis into a graph later is painful; carrying two extra fields from day one is free. See §12.

### 6.2 Edge types

```
EVIDENCED_BY    Claim ──► EvidenceSpan          the provenance edge
DERIVED_FROM    any ──► any                     the inference edge; T4 requires it
LADDERS_UP_TO   Need ──► Need                   laddering (p. 41)
REQUIRES        Need ──► Need                   B is worthless until A is met (p. 43)
ADDRESSES       FeatureIdea ──► Need
CONTAINS        FeatureIdea ──► FeatureChunk
REALISES        Story ──► FeatureChunk
MEASURED_BY     Need ──► Rating
CLASSIFIED_AS   Need ──► KanoClass
SERVED_BY       Need ──► Alternative
CONTRADICTS     Claim ──► Claim                 preserved, never averaged
TESTED_BY       Hypothesis ──► Test
DECIDED_BY      any ──► Decision
FLAGGED_BY      any ──► Finding
SUPERSEDES      any ──► any                     revision without deletion

── brownfield ──
CURRENT_STATE   ProcessModel ──► IncumbentSystem
FUTURE_STATE    ProcessModel ──► ValueProp
PAIN_AT         Need ──► ProcessStep            where the pain actually occurs
SATISFIED_BY    Need ──► IncumbentSystem        the incumbent as the alternative
CONSTRAINED_BY  Story|Need ──► Constraint
EVIDENCES_NEED  Workaround ──► Need             shadow process as proof of unmet need

── continuity ──
DEPENDS_ON      Story|Chunk ──► Dependency
BASELINED_AS    any ──► Baseline
VARIES_FROM     any ──► Baseline                carries a Variance
IMPLEMENTS      BuildPhase ──► Story
OBSERVED_AS     Story ──► DeliverySignal

── federation ──
CLAIMED_BY      any ──► Partition               scope ownership
CONFLICTS_WITH  any ──► any                     cross-partition collision
```

Nothing is ever deleted. Revision is `SUPERSEDES` — which is what makes *"what did we believe on day 12, and why did it change"* answerable, and is the substrate the post-mortem and the RTM both run on.

### 6.3 Storage

`graph.json` is the canonical, portable, schema-versioned artifact. A SQLite mirror exists for query performance and LangGraph checkpointing, and is derived, disposable, gitignored. **The JSON schema is what other people build against, and is versioned independently of the tool.**

---

## 7. Brownfield transformation — a first-class path

Most product work in large organisations is not greenfield. It is modernising an incumbent: a policy administration system, a lending platform, an item data pipeline. The BA's evidence is process documentation, operational data and system behaviour, and the competitor is the client's own software.

Olsen's framework survives this intact — arguably it works better, because satisfaction becomes measurable rather than surveyed. But four things must be modelled explicitly.

### 7.1 The incumbent is the alternative

`SATISFIED_BY: Need ──► IncumbentSystem`. Satisfaction with the current solution is rated from **operational evidence** where it exists:

| Signal | Reads as |
|---|---|
| Cycle time vs. benchmark | satisfaction with speed |
| Rework and error rates | satisfaction with accuracy |
| Ticket volume by category | dissatisfaction, localised |
| Workaround prevalence | severe dissatisfaction — someone built a shadow spreadsheet rather than use the system |
| Abandonment mid-process | the need is not being met at all |
| Manual touchpoints per transaction | satisfaction with automation |

`Workaround` is a node type because a shadow process is the strongest unmet-need evidence available anywhere. Nobody maintains a spreadsheet for fun.

### 7.2 As-is and to-be are graph objects, not diagrams

`ProcessModel` (as-is) is built from documentary and system evidence, with each `ProcessStep` carrying actor, system, pain points and metrics. Needs are generated from **pain at steps** (`PAIN_AT`) rather than from stated desire — which is what a BA actually does, made mechanical and traceable.

The to-be `ProcessModel` is the solution-space counterpart, derived from the committed `ValueProp`. The delta between them is the change the programme is actually making, and it is computable rather than asserted. Both render as diagrams (§14), but the diagram is a projection.

### 7.3 Constraints are not requirements

Regulatory, contractual and policy obligations — DPDP, IRDAI, RBI circulars, PCI-DSS, internal risk policy — are `Constraint` nodes. They differ from needs in three ways: they cannot be traded off against ROI, they carry a source document rather than a customer, and **an untraced constraint is an audit finding waiting to happen.**

I8 makes this mechanical: every `Constraint` must trace to at least one `Story`, or `ConstraintCritic` blocks at G4. This is also, not coincidentally, exactly the query an auditor runs.

### 7.4 Migration is a dependency class

Cutover, data migration, parallel run, decommissioning and reconciliation are `Dependency` nodes of kind `migration`. They are the single most commonly under-planned thing in transformation programmes and they belong in the MVP gate conversation, not in a mobilisation deck three months later.

### 7.5 What changes for the operator

Nothing about the process shape. `probative init --brownfield` changes which evidence kinds are prioritised, adds the as-is phase before segment definition, points the satisfaction axis at the incumbent, and turns on constraint tracing. Same gates, same formulas, same critics plus one.

### 7.6 Onboarding mode — reconstructing intent from what survives

A product manager joins a brownfield project. The previous one has gone, or handed over almost nothing. What exists is documentation of unknown currency, a codebase, a Jira project with four years of history, and a team who will answer questions but whose patience is a finite budget.

`probative onboard` runs the same graph backwards: from surviving artifacts to reconstructed intent.

**The success condition is not a document.** It is that the new PM can hold a conversation about the product in week two without support. Every choice below serves that and nothing else.

#### The banding is the product

Every reconstructed claim lands in one of three bands, named for the decision the user is actually making:

| Band | Rests on | What they do in a meeting |
|---|---|---|
| **Safe to say** | code running in production, or an explicit decision record | assert it |
| **Say with a caveat** | tickets, PRs, commit history — someone intended this | "as I understand it…" |
| **Ask, don't say** | a plausible reading with thin or conflicting support | bring it as a question |

This maps onto the tier model: T1 `system` evidence → safe; T4 over T1 `delivery` evidence → caveat; T4 with thin support → ask. The band travels with the claim into every artifact, because the whole point is that the user knows which sentences are load-bearing before they open their mouth.

A reconstruction that is wrong through lack of context is acceptable and expected. A reconstruction that is wrong *and unmarked* is the failure.

#### Where the evidence hides

| Source | What it actually tells you | Band it supports |
|---|---|---|
| **Test names** | The most honest specification in any codebase. `test_policy_cannot_be_issued_without_underwriter_approval` is a business rule that CI has been enforcing for years | safe |
| **Feature flags** | A flag at 100% for two years is a decision nobody wrote down. One stuck at 5% for eighteen months is a failed experiment nobody closed | safe / caveat |
| **DB migrations** | A timeline of which concepts entered the product and when. Nullable columns nothing writes to are abandoned intent | safe |
| **Won't-Fix and stale tickets** | The refusal list, recovered from the wreckage. Scope that sat in Ready for Dev for eight months and died | caveat |
| **Reopen counts** | A ticket reopened four times is not a bug, it is an unresolved disagreement with a ticket number | caveat |
| **PR review threads** | Where real decisions were made and never reached a document. "We decided against X because Y", fourteen months ago | caveat |
| **Doc view counts and edit history** | A page claiming authority that nobody has opened in a year is a fossil. The three pages people actually read are the real documentation | caveat |
| **Absences** | No accessibility tickets ever. No security review in the whole history. No tickets originating from an entire user type. Nobody looks for these and they are cheap to compute | ask |
| **Contradictions** | The PRD says X, the code does Y, the tickets say Z. Existing `CONTRADICTS` machinery. For a new PM this is the highest-value output, because contradictions are where they will be burned in public | ask |

#### Posture — I9

The tool never says a past decision was wrong. It says what appears to have been decided and what that rests on. `RedTeam` is disabled in this mode; `NeutralityCritic` blocks evaluative language and any claim that attributes fault to a person.

This is not politeness. The user is new, has no political capital, and will be reading this output next to people who made those decisions. A tool that hands them a critique of their predecessor is a tool that gets them into trouble in week one, and they will never open it again.

The people map is the sharp edge here. Contributor activity per area, and who has left, is genuinely useful — it tells the new PM where knowledge has already walked out of the building and where to be least confident. The same data phrased as performance commentary is unusable. The distinction is: **map where knowledge lives, never who did well.**

#### Conversation prep

The feature that serves the win condition directly:

```bash
probative onboard brief --topic payments
```

Returns, for that area: what they can safely assert, what is worth caveating, the three questions worth spending social capital on, and who uniquely holds what. A new PM's scarcest resource is not information — it is knowing which questions are worth asking and of whom.

#### What it produces

A reconstruction pack: product map, glossary of the team's actual vocabulary with first appearance and who introduced it, decision log with what each decision rests on, contradiction list, absence list, people-and-knowledge map, and the ranked question list.

#### And then it feeds the forward pipeline

The corrected reconstruction **is the as-is model** (§7.2). Path C assumes you can hand it process documents and already know what they mean; onboarding mode produces the understanding Path C assumes.

There is a second-order effect worth naming. Once colleagues have corrected the reconstruction, it becomes the team's first real baseline (§10) — the thing a long-running project almost never has, and the thing variance tracking needs in order to exist at all. **The onboarding exercise creates the baseline the project was missing.**

---

## 8. The deterministic layer

Every formula is a registered pure function in `probative/formulas/`, unit-tested against the worked examples in the book. Agents call them; agents never compute.

| `formula_id` | Definition | Source |
|---|---|---|
| `gap` | `importance − satisfaction` | p. 56 |
| `ulwick_opportunity` | `importance + max(importance − satisfaction, 0)` — 0–20 on 0–10 inputs; >15 very attractive, <10 unattractive | p. 57 |
| `customer_value_delivered` | `importance × satisfaction` | p. 60 |
| `opportunity_to_add_value` | `importance × (1 − satisfaction)` | p. 60 |
| `customer_value_created` | `importance × (sat_after − sat_before)` | p. 62 |
| `roi` | `return / investment` (developer-weeks) | p. 81 |
| `approximate_roi` | 3×3 value/effort grid → rank 1–9 | p. 84 |
| `kano_classify` | functional × dysfunctional pair → six-outcome table | Ch. 4 |
| `hierarchy_discount` | discounts a need when a `REQUIRES` predecessor is unmet | p. 43 |
| `invest_score` | rubric over the six INVEST properties | p. 78 |
| `incumbent_satisfaction` | operational signals → satisfaction estimate with confidence band | v0.3 |
| `process_delta` | as-is vs to-be step difference | v0.3 |
| `blast_radius` | transitive closure of dependent nodes | v0.2 |
| `variance_severity` | `blast_radius_weight × baseline_commitment_weight` | v0.2 |
| `partition_conflict` | cross-partition collision detection | v0.3 |

Two scoring philosophies coexist deliberately: `ulwick_opportunity` and `opportunity_to_add_value`. They rank differently in edge cases. **Both are computed and both are shown.** Disagreement on the top five surfaces as a `Question` — a useful signal that the underlying ratings are not discriminating.

Ratings carry uncertainty. With n=8, an importance mean of 7.2 is a range. Ratings store `n`, `dispersion`, `tier` and `kind`; every plotted point renders with a confidence envelope sized accordingly. Olsen's *"doing quant on qual"* (p. 55) made explicit rather than fudged.

---

## 9. Runtime architecture

### 9.1 Topology

LangGraph, with an explicit phase state machine rather than free-form supervisor routing.

```
                ┌──────────────────────────────────────────────┐
                │                 PHASE k                      │
   state ──►    │  Producer ──► FormulaValidator ──► Critics   │
                │      ▲              │  (deterministic)  │    │
                │      │              ✗                   │    │
                │      └──── repair ◄─┴───────────────────┘    │
                │                     │ (max 3 cycles)         │
                │                     ▼                        │
                │             Gate ──► Committer ──► Variance  │
                └─────────────────────┬────────────────────────┘
                                      ▼
                                  PHASE k+1
```

- **Critics fan out in parallel** and are joined; each returns `Finding[]` with `severity ∈ {block, warn, note}` and a required remedy.
- **The repair loop is machine-side.** The patch returns to the producer with findings attached, capped at 3 cycles. The human sees a critic only when it still blocks after three attempts.
- **Gates** use `interrupt_before` — a run genuinely pauses and resumes days later from the SQLite checkpoint.
- **Budget** is enforced per phase in tokens and wall-clock. On exhaustion the system degrades explicitly and records that it did so. It never silently truncates.

### 9.2 Phases

```
P0  ingest + evidence sufficiency
P1  as-is process model                  [brownfield only]
P2  segment + proto-persona              → G1
P3  needs, ladders, hierarchy, ratings   → G2
P4  value proposition + refusal list     → G3
P5  features, chunks, ROI, MVP,
    dependencies, constraints, premortem → G4
P6  story map + stories + AC             → G5
P7  to-be process model + phase plan     → G6
```

### 9.3 Gates

| Gate | The question | Solo | Enterprise |
|---|---|---|---|
| **G0** | Enough evidence to proceed, and in what mode? | auto | auto + record |
| **G1** | Is this the target customer? | human | human + sign-off |
| **G2** | Is this the need set, and are the ratings honest? | human | human + sign-off |
| **G3** | What are we deliberately refusing to do? | human | human + sign-off |
| **G4** | Is this the minimum set? Dependencies owned, constraints traced? | human | human + sign-off |
| **G5** | Ship into the tracker? | merged into G4 | human + sign-off |
| **G6** | Hand off to build? | auto | human + sign-off |

G3 is the one Olsen would insist on: *"Strategy means saying no"* (p. 68). The refusal list is a first-class output. G4 blocks on unowned dependencies (§11) and untraced constraints (I8).

### 9.4 Premortem and postmortem

**Premortem** runs before G4 commits: *it is twelve weeks later and this failed — write the story of why.* Outputs are typed nodes bound to specific `Hypothesis`, `Dependency` and `Constraint` nodes, each with a leading indicator. Four minutes, and the highest-value four minutes in the run.

**Postmortem** is computed, not convened. When delivery signals arrive, `PostmortemAnalyst` reconciles `Baseline` against `DeliverySignal`: what was planned, what shipped, what changed, when, who decided, and which premortem predictions came true. Not a facilitation — a reconciliation that a retro can then argue about. Most retros fail because the first forty minutes go on reconstructing what happened.

### 9.5 The tedium budget

Spec Kit and BMAD become abandonware the same way, and the mechanism is understood:

| Source of tedium | Answer |
|---|---|
| **Authoring burden** — humans write and maintain markdown | Humans *decide*, never author. Accept / reject / amend on a proposed patch, never a blank page. **Zero required free-text documents** |
| **Ceremony before value** — five steps before anything useful appears | `probative critique` gives a scored teardown in one command with no setup. Within a run, every phase renders immediately |
| **Rot** — docs drift; updating is manual, so people stop | Artifacts are derived and cannot rot independently. When reality changes the system recomputes and offers a delta to confirm |

**The principle: machine-side rigour, human-side brevity.** Fourteen critics and seven gates sounds heavy and is not, because critic load is borne by the repair loop. The human is interrupted only by a decision that is genuinely theirs.

| Metric | Target |
|---|---|
| Time to first useful artifact | < 60 s (`probative critique`) |
| Human interactions, full solo run | ≤ 40, gates ≤ 5 |
| Required free-text authoring | 0 documents |
| Touches to absorb an upstream change | ≤ 1 confirmation per affected baseline |
| Median gate decision time | < 90 s |

`TediumAuditor` measures actual counts and flags phases over budget. A system that enforces rigour on its user should measure the cost it imposes; if the numbers worsen between releases, that is a regression like any other.

### 9.6 Modes

| | **Solo** | **Team** | **Enterprise** |
|---|---|---|---|
| Operators | 1 | 2–4, one partition | many, federated (§12) |
| Gates | 4 | 6 | 7 + sign-off records |
| Critics | 5 core | 9 | all 14 |
| Elicitation | 12–15 min adaptive | 20 min | structured, multi-stakeholder |
| Evidence | T3-heavy typical | mixed | T1/T2-heavy, volume ingestion |
| Constraints | optional | flagged | traced, I8 enforced |
| Dependencies | flagged | flagged + owned | owned + escalation + RAID export |
| Tracker | CSV export | export + read-back | read-back + area/iteration mapping |
| Audit | run manifest | + decision log | + immutable sign-off trail, RTM, retention policy |

Mode changes ceremony, never maths. An enterprise programme and a solo founder get identical opportunity scores from identical inputs — which is, in itself, slightly subversive.

---

## 10. Continuity: baseline, signal, variance

### 10.1 Why baselines

Nobody reconciles plan against outcome, and the reason is not laziness — the plan was never captured in a form a machine could compare anything to. A slide deck is not a baseline. A frozen, content-addressed subgraph with a human decision attached is.

### 10.2 What a baseline is

A gate commit freezes a `Baseline`: a content-addressed snapshot of every node in scope at that moment, with the `Decision` attached. Baselines are never edited, only superseded with a recorded reason.

### 10.3 Delivery signals

Opt-in, read-only, one-directional: status read back from Jira/ADO/Linear or from build-phase completion, written as `DeliverySignal` nodes. The system never writes work items on a schedule and never manages your board. **If it starts managing boards, it has failed.**

### 10.4 Variance

Every committed change — human or signal — computes variance against every live baseline, synchronously, as part of the commit.

```
kind          added | removed | modified | reprioritised | unsupported
node          what changed
baseline      which commitment it violates
blast_radius  the transitive set of downstream nodes affected
severity      blast radius × baseline weight
rationale     required if human-initiated; inferred if signal-initiated
```

This is the whole answer to failure mode 6. A scope change cannot be *late*, because the notification is a side effect of the change. If a need's importance drops and three MVP stories rested on it, you learn at the moment the rating changes, with the three stories named.

---

## 11. Dependencies as first-class objects

```
kind        team | system | vendor | data | legal | regulatory | infra | migration
direction   inbound (we need) | outbound (they need us)
owner       required before G4 commits — a name, not a team
status      unowned | owned | agreed | at-risk | resolved
by_when     required if owned
evidence    what tells us this dependency exists
```

`DependencyMapper` proposes them by inspecting stories, chunks, process models and evidence for boundary language — external systems, third parties, uncontrolled data, approvals, cutover. `DependencyCritic` **blocks G4 on any dependency with `status: unowned`**.

Deliberately annoying at exactly one moment — MVP commit — because that is the last cheap moment to discover it. Solo mode flags but does not block; a solo founder's dependency owner is always themselves.

---

## 12. Federated ownership and semantic merge

### 12.1 The real shape of the problem

A 200-person programme has several PMs and BAs. Each owns a scope area — a value stream, a workstream, a module. They work independently most of the time, and they collide at the boundaries: two BAs claim the same need, one's rating change invalidates another's MVP selection, a dependency's two ends disagree about its status, a story survives in one partition while the need justifying it was retired in another.

This is **not** fine-grained co-editing. Nobody needs to watch another BA's cursor. It is coarse-grained partition-and-merge with semantic reconciliation — which is the shape of git, and can be built the same way: no server, no accounts, a shared remote everyone already has.

### 12.2 Partitions

Every node carries `partition` and `owner`. A partition is a named scope area with a declared boundary — the segments, needs and process areas it claims. Partitions are files; a run operates on one partition plus a read-only view of the others.

### 12.3 Merge is semantic, not textual

This is the part git cannot do. A text merge sees two changed lines. Probative sees:

| Conflict | Detected by |
|---|---|
| Two partitions claim the same `Need` | `CLAIMED_BY` collision |
| Contradictory ratings on a shared need | `CONTRADICTS` + tier comparison |
| A dependency whose ends disagree on status or owner | `DEPENDS_ON` reconciliation |
| A story whose justifying need was retired elsewhere | orphan detection via `REALISES` → `ADDRESSES` |
| Overlapping MVP claims on one team's capacity | `Estimate` roll-up across partitions |
| A constraint traced in one partition, ignored in another | I8 across the union |

Merge output is a **cross-partition variance report**, not a diff — the same machinery as §10.4, applied across owners instead of across time. Conflicts route to the two owners with the evidence for each side attached.

Git will happily merge two BAs' work and tell you nothing. Probative tells you that BA-A's satisfaction revision on *"reduce time to issue a policy"* just moved three of BA-B's stories out of the MVP. That is the difference, and it is only possible because the artifacts are projections of a typed graph rather than documents.

### 12.4 What ships when

Partition and owner fields ship in **v0.1** — they cost two fields and retrofitting an ownership axis later is expensive. Merge mechanics ship in **v0.2**, because you cannot meaningfully test a merge until two real partitions exist, and they will not exist until someone uses it.

---

## 13. The agent roster

### Evidence

| Agent | Does |
|---|---|
| `Ingestor` | PDF, DOCX, XLSX, CSV, Markdown, Confluence export, Jira/ADO export, images → `Source` + `EvidenceSpan`, classified by tier and kind |
| `Elicitor` | Structured interrogation → T3. See §13.1 |
| `DeskResearcher` | Web and MCP research → T2 with URL, timestamp, content hash |
| `EvidenceLedger` | Dedupes, resolves entities, detects contradictions, computes corroboration |

### 13.1 The Elicitor

For the solo case this agent *is* the product's intelligence. It is not a form — it is a structured interview whose job is to extract what a practitioner knows but has not articulated, and to find where they are guessing and get them to admit it.

- **Adaptive depth.** Stops when marginal information gain falls below threshold. Gain is measurable: an answer changing no downstream value was a wasted question, and wasted questions are I6 violations.
- **Basis capture.** "Seen across four client engagements" and "seems likely" are different evidence carrying different weight.
- **Permission to not know.** `unknown` is valid and non-failing; it converts to a `Question` plus a research task. A system that accepts a confident non-answer is worse than one that asks nothing.
- **Challenge in the moment.** When an answer contradicts ingested evidence, it says so and shows the quote.
- **Itself audited.** `BiasHunter` reviews the transcript for leading questions. An agent that interrogates the user can lead the witness, and if it does, the T3 evidence is contaminated at source.

### Brownfield

| Agent | Does |
|---|---|
| `ProcessMapper` | Builds as-is `ProcessModel` from documentary and system evidence; extracts actors, systems, pain, metrics |
| `IncumbentRater` | Derives satisfaction from operational signals (§7.1) with confidence bands |
| `WorkaroundHunter` | Finds shadow processes in tickets, spreadsheets and interview language — the strongest unmet-need evidence there is |
| `ConstraintTracer` | Extracts obligations from regulatory and contractual documents; maintains constraint → story traceability |
| `ToBeModeller` | Derives the to-be process from the committed value prop; computes the delta |

### Problem space — Olsen 1–2

`SegmentHypothesizer` · `PersonaSynthesizer` · `NeedExtractor` · `Ladderer` · `HierarchyMapper` · `RatingElicitor` · `OpportunityScorer` *(pure function)* · `KanoClassifier` · `JourneyMapper` · `EmpathyMapper`

### Solution space — Olsen 3–5, Patton

`ValuePropDefiner` · `FeatureIdeator` · `Chunker` · `Estimator` · `ROIPrioritizer` *(pure function)* · `MVPSelector` · `StoryMapper` · `StoryWriter` · `TestDesigner`

### Continuity and federation

`DependencyMapper` · `BuildPhasePlanner` · `VarianceMonitor` · `PremortemFacilitator` · `PostmortemAnalyst` · `MergeReconciler`

### Critics — each with a rubric and veto authority

| Critic | Mandate | Severity |
|---|---|---|
| `EvidenceAuditor` | I1, I4. Unsourced claims, authored numbers, citations that don't support what they're cited for | block |
| `SpaceWarden` | I3. *"One of the easiest ways to tell that a product team is starting with the solution space is that instead of articulating customer benefits, they list product features"* (p. 39) | block |
| `SegmentSkeptic` | A segment — differing needs and behaviour — or a demographic bucket? | block |
| `ConstraintCritic` | I8. Untraced obligations at MVP commit | **block at G4** |
| `DependencyCritic` | Unowned cross-boundary dependencies at MVP commit | **block at G4** |
| `BiasHunter` | Sampling, survivorship, confirmation bias; leading questions in elicitation | warn → block on sampling |
| `ProcessCritic` | As-is models asserting steps no evidence supports; to-be models that quietly keep the pain | warn |
| `LadderCritic` | Distinct benefits or restatements? Ladders collapsing prematurely? | warn |
| `KanoTimeCritic` | Delighters decay into must-haves (p. 65) | note |
| `HierarchyCritic` | Investing in a higher-tier need while a lower one is unmet (p. 44) | warn |
| `INVESTCritic` | Story quality; testability especially | block on untestable |
| `RedTeam` | Mandate: kill this. Strongest counter-case, named failure modes, "what would have to be true" | warn |
| `Falsifier` | Cheapest disconfirming test per load-bearing hypothesis | block if none exists |
| `DriftCritic` | Post-commit: which downstream nodes just lost their justification? | warn |
| `TediumAuditor` | Interaction count per phase against the I6 budget | note → warn |

**Critic calibration is itself a risk.** A critic blocking everything is as useless as one blocking nothing, and LLM critics drift toward finding fault to appear useful. All are evaluated against the seeded-defect corpus (§17) on catch rate *and* false-positive rate, and both numbers ship in the README.

---

## 14. Artifacts

All artifacts are projections (I5). The renderer has no free-text slots.

| Format | Purpose |
|---|---|
| `graph.json` | Canonical, portable, schema-versioned — what others integrate against |
| `*.md` | Human-readable, diffable, PR-reviewable; provenance as footnotes `[T1·customer·0.82]` |
| `*.html` | Single-file interactive, no build step, no CDN |
| `*.pdf` | Interactive — internal links, form fields for gate sign-off, provenance appendix |
| `*.csv` / `*.xlsx` | Tracker import, RTM, RAID (§15) |
| `*.mmd` / `*.svg` | Process models as diagrams |

### 14.1 Product artifacts

- **Opportunity landscape** — Olsen's importance/satisfaction scatter (Fig. 4.4), interactive: rectangle-area rendering of `customer_value_delivered` and `opportunity_to_add_value` on hover, confidence envelopes sized by n and tier, quadrant labels, T5 ghosts where enabled.
- **Provenance story map** — backbone and release grid, every card coloured by the tier of its weakest support. Click a card: a drawer with the actual quote and the chain evidence → need → chunk → story.
- **Assumption ledger** — every hypothesis the plan rests on, ranked by what breaks if false, each with its test and cost.
- **Variance ledger** — what changed against each baseline, when, who decided, what it cost downstream.

### 14.2 BA-native artifacts

These are the ones that make an enterprise BA's job legible, and all four are projections rather than new machinery.

- **Requirements traceability matrix.** Constraint / need → value prop → feature chunk → story → acceptance criterion → delivery signal, with evidence at the left-hand end. Every BA on a regulated programme already keeps one by hand in a spreadsheet that is wrong within a fortnight. **This one is derived, so it is correct by construction** — and it is the artifact that makes an auditor's question a query rather than a week.
- **RAID log.** Nearly free: Risks from `RedTeam` and `Premortem`; Assumptions from the assumption ledger; Issues from open `Question` nodes and unresolved variance; Dependencies from §11. Exports to XLSX in the shape a PMO expects.
- **As-is / to-be process models.** Rendered from `ProcessModel`, with pain points and metrics annotated on as-is steps and the delta highlighted on to-be. Mermaid by default; BPMN-lite later if anyone asks.
- **Gap analysis.** The computed delta between as-is and to-be, expressed as the needs it addresses and the constraints it satisfies — the document a transformation programme is usually funded on, and usually written by hand from memory.

The RTM is the sharpest opening line this product has for an enterprise buyer, and it is nearly free given the graph. *"Your traceability matrix maintains itself"* lands with a BA in a way that nothing about personas ever will.

---

## 15. Tracker interop

Asked at run start: **Jira · Azure DevOps · Linear · GitHub Issues · CSV only.**

**Jira CSV:** `Issue Type, Summary, Description, Parent, Epic Link, Labels, Story Points, Acceptance Criteria, probative-id`
**ADO CSV:** `Work Item Type, Title, Description (HTML), Area Path, Iteration Path, Parent, Effort, Acceptance Criteria`

Two things most exporters get wrong:

1. **Idempotency.** Every item carries a stable `probative-id`; the run directory keeps a ledger mapping node id → tracker key. A second export produces a **diff plan** — create / update / skip — printed for approval. Nobody's backlog gets 90 duplicates.
2. **Provenance survives the boundary.** Each story's description ends with a compact footer: the need it serves, its evidence tier and kind, any constraint it satisfies, and a link back to the HTML artifact. An engineer asking "why are we building this?" gets an answer inside Jira.

Stories resting only on T5 are excluded and cannot be forced. Stories resting only on T3 export with an amber marker. Read-back is opt-in and one-directional: status in, nothing out.

---

## 16. Distribution and interfaces

Core is a library. Everything else is a skin over it, and the skin a person uses is the only thing they ever see.

```
probative-core (Python)    graph · formulas · validators · agents · renderers
        │
  ┌─────┼───────────┬──────────────┬─────────────────┬──────────────┐
  ▼     ▼           ▼              ▼                 ▼              ▼
 CLI   MCP server  plugin skin   GitHub Action   library import   (future) binaries
```

### 16.1 How someone actually gets it

| Surface | Who it is for | What they do |
|---|---|---|
| **One-shot run** | anyone evaluating it | `uvx probative critique prd.pdf` — no install, no virtualenv, under a minute from landing on the README |
| **Installed CLI** | operators using it repeatedly | `uv tool install probative`, or pipx |
| **MCP server** | Cursor, Claude Desktop, Claude Code, any MCP client | `probative mcp` over stdio, with a config snippet in the README |
| **Plugin skin** | PMs and BAs already working inside Claude | install from a marketplace; slash commands, no terminal |
| **GitHub Action** | teams keeping specs in git | critique runs on any PR touching a spec and posts findings as review comments |
| **Library** | people building on the graph | `from probative import …`; the `graph.json` schema is the real integration surface |

Two commands need no project and no setup: `critique` and `onboard` (§7.6). They are the two doors strangers come through.

The one-shot run is the most important line in that table. Time-to-first-artifact is an I6 metric, and `uvx` makes it a single command with nothing to undo if the person walks away.

### 16.2 The honest gap

**The primary operator is a PM or BA, and a meaningful fraction of them cannot install a Python CLI.** Locked-down enterprise laptops, no admin rights, no terminal habit — exactly the population in the regulated-transformation case this product is otherwise well suited to.

The plugin path is the real answer for those people, but only if they already use Claude Code or Cowork, which is a much smaller population than "PMs and BAs" in general.

So the reachable audience in v0.1 is narrower than §1.1's stated audience: **PM/BAs who are either comfortable with a terminal or already working inside Claude.** That should be said plainly rather than discovered later.

Options for closing it, none of them in v0.1:

- **Signed standalone binaries** (PyInstaller or Nuitka). One download, no Python. Works on a locked-down machine only if it is code-signed, which costs money and a certificate.
- **The plugin path becoming primary**, as assistant adoption grows inside enterprises. Plausible, but not something to depend on.
- **A hosted version.** Contradicts the no-server non-goal (§2.2) and is squarely wevit-shaped (R7).
- **Someone technical runs it and the BA consumes the artifacts.** This works today and requires nothing — but it inverts the operator/beneficiary model in §1.1, because the person driving is then an engineer and the BA becomes a beneficiary of their own discovery process. Acceptable as a stopgap, corrosive as a design assumption.

**This is why PB33 and PB34 sit immediately after PB9 rather than at the end of the roadmap.** The plugin is not a nice-to-have distribution channel; for a large part of the intended audience it is the only door that opens.

---

## 17. The eval harness — where the moat actually is

Code gets forked. The defensible asset is **the definition of quality**, and no one has written it. There is no benchmark for "is this persona any good," which is why every AI PM tool can claim excellence and none can demonstrate it.

**Corpus.** Olsen's MarketingReport.com case study (Ch. 11) as gold reference; public product post-mortems where the missed need is documented in hindsight; open app-review datasets with a hand-labelled need set; **and a brownfield case** — a process document set with a known as-is/to-be delta, which greenfield corpora cannot provide.

| Metric | Definition |
|---|---|
| Provenance precision | % of claims whose cited span actually entails the claim |
| Fabrication rate | claims with no valid support reaching an artifact — target zero, measured, published |
| Need coverage | recall against the gold need list |
| Ranking correlation | Spearman ρ between produced and gold opportunity ranking |
| Constraint recall | % of known obligations extracted and traced |
| INVEST conformance | rubric score across generated stories |
| **Seeded-defect catch rate** | see below |
| Critic false-positive rate | blocks raised on clean input |
| **Human interactions per run** | I6 conformance |
| **Time to first artifact** | I6 conformance |
| Cost per run | tokens and wall-clock to a committed story map |

**Seeded defects.** Inject known faults into a clean corpus: a solution-shaped need, a fabricated statistic with a plausible citation, a demographic-only segment, a story tracing to nothing, a delighter asserted as durable, an unowned dependency, an untraced regulatory obligation, a to-be process that preserves the original pain, a leading question in the elicitation transcript. Measure what each critic catches.

Nobody else can quote these numbers. It is publishable standalone, and it turns critic quality from a claim into a regression test. **Whoever writes the benchmark defines the category.**

---

## 18. Roadmap

### v0.1

**Slice C — `probative critique` (weeks 1–3, ships first)**
Point it at a document that already exists — Confluence PRD, Jira/ADO export, raw high-level stories, unstructured PDF / XLSX / CSV / Markdown — and get a teardown that is **scored, with qualitative depth where a number would flatten something**: headline scores per dimension for triage, prose findings with quoted evidence where it matters.

Critics: `EvidenceAuditor`, `SpaceWarden`, `SegmentSkeptic`, `INVESTCritic`, `DependencyCritic`, `ConstraintCritic`, `RedTeam`.

No graph construction, no seed-data ceremony, no long run. Immediate utility to someone who has never heard of the project — the distribution wedge, and the thing that forces the critic rubrics and `Finding` model into existence early.

**Slice A — the spine (weeks 3–9)**
`ingest → evidence ledger (tier + kind) → elicitation → as-is process model → needs → ladders → ratings (customer or incumbent) → opportunity scoring`, plus the opportunity landscape and needs table. Brownfield path included: `ProcessMapper`, `IncumbentRater`, `WorkaroundHunter`, `ConstraintTracer`.

**Slice B — the tail (weeks 9–14)**
`value prop → feature ideas → chunks → ROI → MVP → dependencies → constraints → premortem at G4 → story map → export`, plus the provenance story map, RTM and RAID.

**In v0.1 because retrofitting is expensive:** `partition` and `owner` on every node; `evidence_kind`; `Constraint` and `ProcessModel` node types; baselines at every gate.

**Deliberately thin in v0.1:** proto-personas only; journey and empathy maps as simple projections; value prop as a structured decision record; process models render but are not hand-editable; no T5; CSV export only; no read-back; no merge mechanics; no web UI.

### v0.2 — handoff and federation
`BuildPhasePlanner`: committed story map → phase plan, each item carrying its story id and provenance chain. Semantic merge and cross-partition variance (§12). Tracker read-back.

### v0.3 — the loop closes
Variance ledger in anger, scope-change alerts, computed post-mortem, dependency roll-up, gap analysis against delivered state.

### Scope honesty

v0.1 is now four workstreams: critique, the evidence spine, brownfield, and BA artifacts. That is a fourteen-week v0.1 and it should be called that rather than pretended into twelve.

Two things make it survivable. The BA artifacts are projections — RTM and RAID are days, not weeks, *if the graph is right*. And brownfield is mostly additional node types and one new agent cluster feeding the same downstream machinery; it is not a parallel pipeline. **If the graph turns out wrong, Slice B slips.** Better than four shallow workstreams.

---

## 19. Methodological provenance

A system that enforces citation should cite itself.

| Element | Source | Status |
|---|---|---|
| PMF pyramid, six-step process, importance/satisfaction, opportunity scoring, benefit ladders, needs hierarchy, MVP chunking, ROI prioritisation, MVP test matrix | Olsen, *Lean Product Playbook* | **Core**, as specified |
| Opportunity score formula | Ulwick, *What Customers Want*, via Olsen p. 57 | Core |
| Kano model | Noriaki Kano, via Olsen Ch. 4 | Core |
| INVEST | Bill Wake, via Olsen p. 78 | Core |
| **Story mapping** | Jeff Patton | **Imported.** `MVP set → backbone → walking skeleton` is our join; needs its own critic rules |
| **Empathy map** | XPLANE / Osterwalder | **Imported.** `thinks` and `feels` are inferential, marked T4 — likeliest fabrication site, strictest tier policy |
| **Journey map** | General UX practice | **Imported.** No canonical source; stages must be evidence-bound or hypothesis-typed |
| **As-is / to-be, gap analysis, RTM, RAID** | BABOK / general BA practice | **Imported.** Well-defined in practice, no single canonical source; the graph makes them derived rather than authored |
| Proto-persona | Jeff Gothelf | Imported, used precisely |
| Pre-mortem | Gary Klein | Imported as a gate ritual, not a document |

Imported elements are where the methodology is thinnest and fabrication risk highest. They get the tightest tier policy, not the loosest.

---

## 20. Decisions

### Resolved

| # | Decision | Resolution |
|---|---|---|
| R1 | Runtime | LangGraph core + MCP server + Claude Code plugin as a thin skin |
| R2 | Operator | PM / BA, sole driver. Engineers, EMs, designers, QA, execs are beneficiaries who never maintain anything |
| R3 | T5 simulated respondents | Quarantined; `blend` never implemented |
| R4 | Critique output style | Scored, with qualitative depth where a number would flatten something |
| R5 | Critique input formats | Confluence PRD, Jira/ADO export, raw stories, PDF, XLSX, CSV, Markdown |
| R6 | Scope boundary | Through the discovery/delivery seam. Not a tracker, not a build tool |
| R7 | wevit.ai | Parked, no coupling. Schema versioned and portable, so open-core stays available |
| R8 | Interactivity in v0.1 | Explorable, not editable-with-writeback |
| R9 | Tracker mapping | Real issue-type hierarchy; read-back deferred to v0.2 |
| R10 | Brownfield | First-class in v0.1 (§7) |
| R11 | BA-native artifacts | In scope. RTM and RAID in v0.1; process models render in v0.1, edit later |
| R12 | Multi-operator | Real. Federated partitions, semantic merge. Schema in v0.1, mechanics in v0.2 |
| R14 | Onboarding mode | Ships as `probative onboard` alongside `critique` and **before** the forward pipeline. Posture is always "this appears to have been decided, here is what it rests on" (I9) | 
| R13 | Name | **Probative**, 2026-09-10. `assay` rejected on collision with `metahub-ai/assay`, a trust layer for AI artifacts in the same ecosystem |

### Open

| # | Decision | Default | Reversible until |
|---|---|---|---|
| D2 | Licence — MIT vs Apache-2.0 vs BSL | Apache-2.0 | first public commit |
| D3 | Elicitation session length | 12–15 min adaptive | v0.1 |
| D4 | LLM provider abstraction depth | LiteLLM-style adapter | Slice A |
| D5 | Does `RedTeam` output ship inside stakeholder artifacts? | yes, as a "least sure about" panel | Slice B |
| D6 | Process model notation | Mermaid; BPMN-lite on request | Slice A |
| D7 | Shared remote for partitions — git, or a filesystem convention? | git | v0.2 |

---

## 21. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Scope.** Four workstreams in v0.1 | **High** | Strict order C → A → B; brownfield rides the same pipeline; BA artifacts are projections; B slips rather than all four going shallow |
| **Tedium creeps back.** Seven gates, fifteen critics, a variance ledger and an RTM is exactly the shape of abandonware | **High** | I6 is a measured invariant with published numbers; critic load stays machine-side; solo mode runs 4 gates and 5 critics |
| **Elicitation fatigue** | High | Adaptive stopping on information gain; resumable; every question must justify itself by changing a downstream value |
| **Critic miscalibration** | High | Seeded-defect corpus with published catch *and* false-positive rate; severity budgets per phase |
| **Merge is harder than it looks** | High | Schema only in v0.1; mechanics in v0.2 against two real partitions. Conflict detection ships before conflict *resolution* — reporting a collision is most of the value |
| **v0.3 pulls the product into delivery management** | High | Read-back one-directional and opt-in. If it starts managing boards, it has failed |
| **Constraint extraction is a liability surface.** Wrongly asserting a regulatory obligation, or missing one | High | Constraints may never rest on T4 inference; every one carries its source document; constraint recall is a published eval metric |
| **Cost and latency** | Medium | Phase budgets, critic sampling on low-stakes patches, resumable checkpoints, per-phase cost printed |
| **Nobody contributes** | Medium | Slice C's standalone utility; exporters, critics and process notations are the natural first PRs, each isolated behind a rubric file |

---

## 22. What "done" looks like

**v0.1, greenfield.** A founder points Probative at a folder — a competitor PDF, two spreadsheets, a Confluence export, and forty minutes of their own answers to hard questions. Twenty minutes and four decisions later: an opportunity landscape where every point traces to something real, a story map whose amber cards are honestly amber, an assumption ledger naming the four things the plan rests on and how to test each cheaply, and a Jira import that does not duplicate next month.

**v0.1, brownfield.** A BA on a policy administration modernisation points it at eleven process documents, a defect export, six months of tickets and the current system's API surface. It comes back with an as-is model annotated with where the pain actually is, satisfaction scores derived from cycle times and workaround prevalence rather than opinion, nine regulatory obligations extracted and traced, and a traceability matrix that was correct the moment it was generated and stays correct.

**v0.2–v0.3.** Eleven weeks later, three cards have quietly changed in the tracker and another BA's rating revision has moved two stories out of scope. They find out the day it happens, with the affected needs named and the dependency identified and owned. When the release ships, the post-mortem is already written — including which of their own premortem predictions came true.

And at every point, when someone asks where a number came from, they click it.
