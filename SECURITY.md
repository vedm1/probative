# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue:
use [GitHub's private vulnerability reporting](https://github.com/vedm1/probative/security/advisories/new)
for this repository, or email the maintainer at muthal.ved@gmail.com.

Include what you found, how to reproduce it, and its potential impact.
You should get an acknowledgement within a few days.

## Scope and data handling

Probative sends the documents you ingest to whichever LLM provider you've
configured — that's how the agents read them. It has no telemetry, no
hosted service, and no account. See `docs/GETTING-STARTED.md` § *Does my
data leave my machine?* for the full answer.

## Supported versions

Pre-1.0: only the latest published release is supported.

## Secrets

No key, token or customer document should ever reach this repository.
`.env` is gitignored; `.env.example` documents the expected keys. If you
believe a secret was committed, report it privately (above) rather than
opening a public issue — even in a since-reverted commit, git history
retains it until the key is rotated.
