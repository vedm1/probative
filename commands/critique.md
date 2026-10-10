---
description: Critique a product document or folder (PRD, spec, Jira/ADO/Confluence export)
argument-hint: <path to a file or folder>
allowed-tools: mcp__plugin_probative_probative__critique
---

Call the Probative `critique` tool with `path` set to: $ARGUMENTS

If no path was given, ask which file or folder to critique, then call the tool. A run takes
up to about a minute; say so once before you call it.

Show the text the tool returns verbatim, then point to the report files it names.

- Do not summarise it. Do not rephrase it. Do not estimate anything.
- Do not add findings, scores or counts of your own, and do not reorder or soften what it says.
- If the tool returns an error, show the error text verbatim and stop. If the error is about
  missing credentials, tell the user to run `/probative:setup`.
