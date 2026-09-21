# Getting started with Probative

> **Status: in development.** This guide describes v0.1 as designed. Phases PB0–PB41 are tracked in [`PHASES.md`](../PHASES.md); nothing is shipped yet. Commands below will firm up as the CLI lands.

Probative walks a product idea from evidence to a story map, using the Lean Product Process. The difference from every other tool that will write you a PRD is that **it refuses to make things up.** Every claim in every artifact either traces to a line in a document you gave it, or is labelled a hypothesis with a test attached.

That means it will sometimes tell you things you'd rather not hear — that your personas rest on nothing, that your top-priority need is a solution in disguise, that you can't export these stories yet. That's the product working, not failing.

---

## 1. Install

Pick whichever fits. You can change your mind later.

**Just trying it out** — nothing to install, nothing to uninstall:

```bash
uvx probative critique your-prd.pdf
```

**Using it properly:**

```bash
uv tool install probative      # or: pipx install probative
```

**No terminal?** Install the Probative plugin from the marketplace in Claude Code or Cowork. Everything below works as a slash command instead, with identical results.

**Then set a key** — Probative talks to an LLM provider of your choosing (Anthropic, OpenAI, Gemini, or a local model):

```bash
export ANTHROPIC_API_KEY=sk-...
# or OPENAI_API_KEY, GEMINI_API_KEY, or point at a local endpoint
```

---

## 2. Your first five minutes

Don't start a project. Start by pointing it at something you already have — a PRD, a spec, a backlog export, a requirements doc. Anything you wrote in the last six months.

```bash
probative critique ~/Documents/checkout-redesign-prd.pdf
```

You'll get something like this:

```
Probative · critique · checkout-redesign-prd.pdf · 18 pages · 41s

  Evidence           38 / 100   ▓▓▓▓░░░░░░
  Problem framing    24 / 100   ▓▓░░░░░░░░
  Story quality      71 / 100   ▓▓▓▓▓▓▓░░░
  Dependencies        —         none declared
  Constraints         —         none found

  4 blocking · 11 warnings · 6 notes

  ✗ BLOCK   Problem framing — 9 of 12 stated "user needs" name a solution
            "Users need a one-click checkout button"            p.4 ¶2
            "Customers need a saved-cards dashboard"            p.5 ¶1
            → A need says what the user gets, not what you build.
              What does one-click checkout give them that they lack?

  ✗ BLOCK   Evidence — 6 quantitative claims have no source
            "73% of users abandon at payment"                   p.2 ¶3
            "Competitors convert 2.4x better"                   p.7 ¶2
            → Neither appears in any cited document. If these came
              from analytics, say which query and when.

  ⚠ WARN    Segment — "users aged 25-45 who shop online" is a
            demographic bucket, not a segment. Nothing here says
            these people have different needs from anyone else.

  Full report → ./checkout-redesign-prd.critique.html
```

### How to read that

- **Scores** are per dimension, so you can see whether the problem is your evidence, your framing, or your stories. They're computed from findings, not judged by a model.
- **Blocks** are things that would stop a real run. **Warnings** are worth fixing. **Notes** are observations.
- **Every finding has a locator.** Page and paragraph, sheet and cell, heading path. If you can't find what a finding is talking about, that's a bug — please file it.
- **The HTML report** is where you'll actually work. Click any finding to see the surrounding text.

### It accepts most things you'll have

PDF, Word, Excel, CSV, Markdown, plain text, Confluence exports, Jira and Azure DevOps CSV exports. Point it at a folder and it takes the lot:

```bash
probative critique ./specs/
```

### If you use nothing else, use this

`critique` needs no setup and no project. Plenty of people will use only this, forever, and get value from it. Everything below is for when you want to go further.

---

## 3. Just joined a project?

If you've inherited something — a product, a backlog, a codebase — and the person who understood it has gone, start here instead.

```bash
probative onboard --jira ./jira-export.csv --repo ~/code/policy-svc --docs ./confluence-export/
```

It reads what survived and reconstructs what appears to have been decided. **It never tells you a past decision was wrong** — only what was decided and what that rests on. You're new, you have no political capital, and a tool that hands you a critique of your predecessor is a tool that gets you into trouble in week one.

### Everything is banded

The point isn't a summary of the project. It's knowing **which sentences are safe for you to say out loud**:

| | Rests on | In a meeting |
|---|---|---|
| **Safe to say** | code running in production, or an explicit decision record | assert it |
| **Say with a caveat** | tickets, PRs, commits — someone intended this | "as I understand it…" |
| **Ask, don't say** | a plausible reading with thin support | bring it as a question |

Some of the reconstruction will be wrong, because context is missing and no tool can invent it. That's fine and expected — what matters is that the uncertain parts are *marked* as uncertain, so a wrong guess costs you a question rather than your credibility.

### What comes out

```
  Reconstruction · policy-svc · 4y 2m of history

  Safe to say ............ 34 claims
  Say with a caveat ...... 61 claims
  Ask, don't say ......... 22 claims

  ⚑ 7 contradictions
    The 2023 PRD says renewals are automatic above ₹2L.
    The code requires manual approval above ₹50L.
    PC-1184 (closed, Won't Fix) proposed changing the threshold.

  ⚑ 4 absences
    No accessibility ticket in four years.
    No ticket originating from the claims team.

  ⚑ 3 areas where the knowledge has left
    Underwriting rules engine — 91% authored by one contributor,
    last active 14 months ago.

  Your 9 questions, ranked → ./onboarding-pack.html
```

**The question list is the real deliverable.** You have a limited budget of other people's patience and no idea yet what you don't know. It ranks the questions by how much each one unblocks and tells you specifically who can answer it.

### Before a meeting

```bash
probative onboard brief --topic payments
```

What you can safely assert about payments, what to caveat, what to ask, and who uniquely knows what. This is the week-two test: can you hold the conversation without support?

### Then keep the reconstruction

Once people have corrected it — and they will, cheerfully, because correcting a diagram is easier than writing one — it becomes your as-is model, and you can run the brownfield path in section 6 straight off it. It also becomes the first real baseline the project has had, which is what makes everything later able to tell you when reality drifts.

---

## 4. Which path are you on?

The full process changes shape depending on what you're starting from. Find yourself here:

| You have… | Your path | Start with |
|---|---|---|
| An idea and no customers yet | **A — from an idea** | `probative init --greenfield` |
| Interviews, tickets, reviews, research | **B — from evidence** | `probative init --greenfield` |
| An existing system you're replacing | **C — from a system** | `probative init --brownfield` |

Paths A and B are the same machinery with different fuel. Path C is the one most large-organisation work actually is, and it's a first-class path rather than an afterthought.

---

## Path A — starting from an idea

You've got a conviction and not much else. This is the honest version of what happens.

```bash
probative init --greenfield
probative ingest ~/research/*.pdf --tier T2 --kind market
probative elicit
```

### The interview is the point

`elicit` is not a form. It's a structured interview whose job is to get what's in your head onto the record — and, just as importantly, to separate what you *know* from what you're *assuming*.

```
  You said brokers lose deals because they respond too slowly.
  How do you know that?

    1  I've observed it directly
    2  Someone in the industry told me
    3  I'm inferring it from something else

> 3

  Recorded as an assumption, not evidence — I've noted it as
  "response latency causes lost deals" with low confidence.

  What's the cheapest way to check it this week? Even three
  brokers would move this from assumption to evidence.

> honestly I don't know any brokers

  Fine — that's an honest answer and more useful than a guess.
  I've logged it as an open question with a research task.

  Next: you've mentioned "slow" three times. Slow compared to
  what? Is there a response time brokers themselves consider
  acceptable, or is that also an assumption?

> also an assumption

  Noted. That's two assumptions holding up your core value
  proposition. They're both cheap to test and I'll put them at
  the top of the ledger.
```

**"I don't know" is a valid answer.** It becomes an open question and a research task. Saying "probably about two hours" when you're guessing is worse than useless, because it gets recorded as if it were true.

The session is resumable — stop whenever, `probative elicit --resume` later. It stops asking about a topic once further questions stop changing anything downstream, so it shouldn't run long.

### Then run it

```bash
probative run
```

You'll be stopped almost immediately:

```
  G0 · Evidence sufficiency

  Customer evidence (T1):     0 sources
  Market evidence (T2):       2 sources
  Your judgement (T3):       14 claims, 11 flagged as assumption

  You can proceed. Everything downstream will be marked as a
  hypothesis, no story will be exportable to a tracker, and the
  opportunity landscape will have no green cells.

  The four assumptions your plan rests on are in the ledger, each
  with a test. Three cost under £200. One needs six brokers.

  Proceed in hypothesis mode?  [y/N]
```

Say yes. Hypothesis mode is legitimate — Dan Olsen is explicit that the framework works *before you talk to a single customer*, precisely because it forces your assumptions into the open where they can be tested. What isn't legitimate is forgetting they were assumptions.

### What you'll have at the end

An opportunity landscape where everything is amber, an assumption ledger ranked by what breaks if each one is wrong, and — most usefully — a short list of the cheapest things you could do next week to turn amber into green.

**You will not get:** a persona (you'll get a *proto-persona*, labelled as such everywhere), or a Jira export. The export refuses, on purpose. Shipping stories built on nothing is the failure this whole tool exists to prevent.

---

## Path B — starting from evidence

You did the research. Now make it count.

```bash
probative init --greenfield
probative ingest ./interviews/   --tier T1 --kind customer
probative ingest ./zendesk.csv   --tier T1 --kind customer
probative ingest ./competitors/  --tier T2 --kind market
probative run
```

### What the tiers and kinds mean

You'll be asked to label what you're feeding in. It takes a second and it determines everything downstream.

**Tier — how direct is this?**

| | |
|---|---|
| `T1` | Straight from the real world: transcripts, tickets, reviews, analytics, incident logs |
| `T2` | Desk research: analyst reports, competitor docs, forum threads |
| `T3` | Your own judgement, captured via `elicit` |

**Kind — what sort of thing is it?**

| | |
|---|---|
| `customer` | Interviews, reviews, support tickets |
| `operational` | Cycle times, error rates, ticket volumes — how the current thing actually performs |
| `documentary` | SOPs, process maps, contracts, regulations |
| `system` | Schemas, APIs, config, legacy behaviour |
| `market` | Analyst reports, competitor teardowns, pricing |

Label honestly. A market report tagged as customer evidence will produce a persona that looks real and isn't.

### Expect it to argue with you

```
  14 needs · 11 respondents · quant-on-qual, n=11

  ⚠ The two opportunity formulas disagree on the top five.

    Ulwick opportunity ranks "reconcile a failed payout" 2nd.
    Olsen opportunity-to-add-value ranks it 6th.

    This happens when importance is high but the spread across
    respondents is wide — 4 people rated it 9+, 5 rated it below 4.
    Your 11 respondents may be two segments, not one.

    Logged as an open question.
```

Both scoring formulas are always computed and always shown. When they disagree, that's usually telling you something real about your data — most often that you have two segments wearing one label. A tool that averaged and moved on would have buried the most interesting finding in your corpus.

**Eleven interviews is enough.** You don't need statistical significance to make progress. Every number is rendered with a confidence envelope sized by how many people said it and how much they disagreed, so you can see exactly how much weight it bears.

---

## Path C — starting from a system that already exists

Most product work in a large organisation is modernising something. Your evidence is process documents and operational data, and your competitor is your own legacy system.

```bash
probative init --brownfield --incumbent "PolicyCentre v7" --mode enterprise
probative ingest ./process-docs/       --tier T1 --kind documentary
probative ingest ./servicenow-6mo.csv  --tier T1 --kind operational
probative ingest ./api-surface.json    --tier T1 --kind system
probative ingest ./irdai-circulars/    --tier T1 --kind documentary --constraints
probative run
```

### Your satisfaction data already exists

This is the good news nobody tells you: you don't need a survey. Satisfaction with the current system is sitting in your ticket queue.

```
  As-is process model · 6 flows · 84 steps

  Pain concentrated at 7 steps, from operational evidence:

    Underwriting referral       cycle 4.2d vs 0.5d target   1,847 tickets
    Document upload             31% rework rate               912 tickets
    Premium recalculation       manual in 68% of cases        —

  ⚑ 3 workarounds detected
    A shared spreadsheet ("UW_Tracker_FINAL_v8.xlsx") is referenced
    in 41 tickets and 2 process documents. Someone rebuilt part of
    the system in Excel. That is the strongest unmet-need evidence
    in this corpus.

  Satisfaction with PolicyCentre v7, derived from operational signal:

    "Issue a policy without re-keying data"    0.22  ▓▓░░░░░░░░
       ← 68% manual recalculation, 31% upload rework
    "Know where a referral is sitting"         0.15  ▓░░░░░░░░░
       ← 4.2d cycle time, 1,847 status-chasing tickets
```

Every satisfaction score shows the signal it came from. You should always be able to argue with the number, which means you should always be able to see what's behind it.

**Workarounds are gold.** Nobody maintains a shadow spreadsheet for fun. If people have rebuilt part of your system in Excel, that's the clearest statement of unmet need you will ever find, and it's usually sitting in plain sight.

### Constraints are not requirements

Feed your regulatory and policy documents with `--constraints` and they become a separate class of thing that can't be traded off against ROI:

```
  ✗ G4 BLOCKED
    2 constraints trace to no story:
      IRDAI Circular 2024/07 §4.2 — grievance acknowledgement SLA
      Internal Risk Policy RP-11 — dual authorisation above ₹50L
    3 dependencies are unowned:
      Data migration from PolicyCentre  (no owner)
      Payment gateway recertification    (no owner)
      Actuarial rate table sign-off      (no owner)
```

Probative will not let you commit an MVP with an untraced obligation or an unowned cross-boundary dependency. This is deliberately annoying at exactly one moment — MVP commit — because that is the last cheap moment to find it. Every later discovery costs more.

A constraint never rests on the model's inference. If it can't find the obligation in a document you gave it, it raises a question instead of asserting a requirement. A hallucinated regulation is a liability, not a feature.

---

## 5. The gates

A run pauses and asks you things. These are the decisions that are genuinely yours:

| | The question |
|---|---|
| **G0** | Is there enough evidence to proceed, and in what mode? |
| **G1** | Is this the target customer? |
| **G2** | Is this the need set, and are the ratings honest? |
| **G3** | **What are we deliberately refusing to do?** |
| **G4** | Is this the minimum set? Dependencies owned, constraints traced? |
| **G5** | Ship this into the tracker? |

Solo runs merge some of these; enterprise mode adds sign-off records.

**G3 is the one that matters most and the one people skip.** It asks what you're saying no to, and the refusal list becomes a first-class output. A value proposition that refuses nothing isn't a strategy, it's a wish list.

Gates use a real pause — you can stop mid-run, close your laptop, and resume days later:

```bash
probative run --resume
```

---

## 6. What you end up with

```
runs/2026-09-17-1430/
├── graph.json                 everything, in one portable file
├── opportunity-landscape.html the importance/satisfaction chart
├── story-map.html             the story map, colour-coded by evidence
├── assumption-ledger.html     what the plan rests on, and how to test it
├── rtm.xlsx                   requirements traceability matrix
├── raid.xlsx                  risks, assumptions, issues, dependencies
├── as-is.mmd / to-be.mmd      process models (brownfield)
├── jira-import.csv            ready to import
└── *.md                       everything above, also as markdown
```

### Reading the colours

One visual language runs through every artifact:

| | Means |
|---|---|
| Solid, dark | Backed by direct evidence (T1) |
| Solid, mid | Backed by desk research (T2) |
| Hatched | Your judgement (T3) — provisional |
| Dotted outline | Inferred (T4) |
| Ghosted | Simulated — never counts toward anything |

Colour is never the only signal; every element also carries a text label and a pattern, so the artifacts work in dark mode and for colourblind readers.

**Click anything.** Every element opens a drawer showing the actual quote from the actual document, and the chain from evidence → need → feature → story. If something isn't clickable, it isn't traceable — and that absence is itself information.

A story map where four cards are green and thirty-one are amber is not a bad result. It's an honest picture of a product plan, probably the first one you've seen.

### The traceability matrix, if you're a BA

You already keep one by hand, in a spreadsheet that's wrong within a fortnight. This one is derived from the graph, so it's correct the moment it's generated and correct again the next time. When an auditor asks which requirement satisfies a given circular, that becomes a lookup instead of a week.

---

## 7. Getting it into Jira or Azure DevOps

```bash
probative export --jira        # or --ado, --linear, --github, --csv
```

Two things worth knowing:

**It won't duplicate.** Every exported item carries a stable id, and a second export shows you a plan before touching anything:

```
  Export plan · Jira

    create   12 stories
    update    3 stories  (acceptance criteria changed)
    skip     18 stories  (unchanged)

  Proceed? [y/N]
```

**Provenance goes with it.** Each story's description ends with the need it serves, its evidence tier, and a link back to the report. When an engineer asks "why are we building this?", the answer is already in the ticket.

Stories resting only on simulated evidence are excluded and can't be forced. Stories resting only on your judgement export with an amber marker, so nobody mistakes them for validated.

---

## 8. In your CI

If your specs live in git:

```yaml
- uses: byndele/probative-action@v1
  with:
    paths: 'specs/**/*.md'
    fail-on: block
```

Every PR touching a spec gets a review comment with the findings. The comment updates in place rather than piling up, and `fail-on: none` makes it advisory if you'd rather not block merges yet.

---

## 9. Questions you'll have

**Why won't it export my stories?**
Because they trace to nothing, or only to simulated evidence. Run `probative why STORY-ID` to see exactly what's missing.

**Why is everything amber?**
You have no T1 evidence. That's normal at the start. The assumption ledger tells you the cheapest way to change it.

**It blocked my gate and I disagree.**
Run `probative gate G4 --explain` for the full reasoning. You can override with `--force`, which records the override, who made it, and why — so it shows up in the post-mortem rather than vanishing. Overriding is a legitimate thing to do; hiding it isn't.

**Does my data leave my machine?**
The documents you ingest are sent to whichever LLM provider you configured — that's how the agents read them. Nothing goes anywhere else: no telemetry, no hosted service, no account. If your material can't leave your network at all, point Probative at a local model; it speaks to providers through an adapter rather than being tied to one. For regulated work, confirm this with whoever owns your data policy before your first run, not after.

**What does a run cost?**
It varies enormously with corpus size. Every phase prints its token and wall-clock cost, and you can cap it:

```bash
probative run --budget-tokens 500000
```

On exhaustion it degrades explicitly — fewer critics, shallower research — and records that it did, rather than silently truncating.

**Can two of us work on the same project?**
Not yet properly. v0.2 adds partitions and semantic merge, where each analyst owns a scope area and merges are reconciled by meaning rather than by text — so it can tell you that a colleague's satisfaction revision just pushed three of your stories out of the MVP. Today, one person drives.

**Why does it keep calling my persona a proto-persona?**
Because no customer evidence stands behind it. A persona with nobody real behind it is a character, and calling it what it is costs nothing and prevents a great deal.

---

## 10. Where to go next

- [`docs/DESIGN.md`](DESIGN.md) — the full design and the reasoning behind every constraint
- [`docs/SCENARIOS.md`](SCENARIOS.md) — the same journeys as acceptance tests
- [`PHASES.md`](../PHASES.md) — what's built and what's coming
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — adding a critic is a rubric file and one method; it's the best first contribution

The method comes from Dan Olsen's *The Lean Product Playbook*, and the book is worth reading whether or not you use this. Probative implements it; it doesn't replace understanding it.
