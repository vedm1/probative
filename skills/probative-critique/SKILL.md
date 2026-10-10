---
name: probative-critique
description: Use when the user shares or points at a product document (PRD, spec, requirements, Jira/ADO/Confluence export, backlog) and wants it checked, reviewed, challenged or stress-tested for unsupported claims, solution-shaped needs, missing evidence or untraced obligations. Runs the Probative critique tool and relays its findings unchanged.
---

# Probative critique

Probative critiques a product document. Every finding quotes the source text it is about, and
every number in the report is computed by code. Your job is to run it and hand over what it
says, not to improve on it.

## How to run it

- Use the `critique` tool with the file or folder path (or inline content with a filename).
   It only reads inside the allowed roots; if it refuses a path, tell the user and suggest
   `/probative:setup` rather than copying the file somewhere else.
- Relay the text it returns verbatim, and name the report files it wrote.
- If it reports missing credentials, point the user to `/probative:setup`.

## Rules that protect the output

- Relay verbatim. Do not summarise, rephrase, reorder or soften findings.
- Never compute, estimate or restate a count or a score of your own. If the user asks how
  many findings there are, read the number from the tool's text.
- A block is a block. Do not describe a blocking finding as minor, and do not offer to clear
  it by editing the document so that it passes.
- Never invent a source, a quote or a citation to resolve a finding. If the document lacks
  evidence for a claim, the honest outcomes are to find the real source, to mark the claim as
  a hypothesis with a test, or to remove the claim.
- The tool judges what a document says, not who wrote it. Do not use its output to evaluate a
  person or a past decision, and do not use it for onboarding-mode reconstruction work.
