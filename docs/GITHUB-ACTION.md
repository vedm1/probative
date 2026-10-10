# Probative on pull requests

A GitHub Action that critiques the spec files a pull request changes and posts the findings
back as review comments. Every finding quotes the line it is about; nothing is a score the
model made up.

## Set it up

1. Add your model key as a repository secret named `ANTHROPIC_API_KEY`.
2. Copy [`examples/probative-critique.yml`](examples/probative-critique.yml) to
   `.github/workflows/probative-critique.yml`.

That is the whole setup. The workflow needs `contents: read` and `pull-requests: write`, and
nothing else.

## What you get

- **Inline comments** on lines the pull request added, one per finding, each with the quoted
  text in a code block, the rule it broke, and the suggested remedy. Blocking findings come
  first.
- **One summary comment**, rewritten in place on every push, with the critique table per file,
  the findings that could not be placed on a line (with the reason), and the files that were
  not critiqued (with the reason).
- A finding is posted once. Pushing again does not repeat comments that are already there, and
  nothing is deleted: a comment whose finding is gone stays until you resolve it.

## When a finding is not inline

It goes in the summary, with its reason: the quote appears more than once in the file, the
text is not something this pull request changed, GitHub sent no diff for the file, the format
has no lines (PDF, DOCX, XLSX), or the run hit `max-inline`. Findings about text the author did
not write are deliberately not turned into line comments.

## Inputs

| Input | Default | |
|---|---|---|
| `anthropic-api-key` | none | pass a secret |
| `paths` | md, markdown, txt, pdf, docx, xlsx | comma-separated globs (`*`, `**`, `?`; no `{a,b}` braces) |
| `max-files` | `25` | the rest are listed as skipped |
| `max-minutes` | `20` | stop starting new files after this; set the job's `timeout-minutes` higher |
| `max-inline` | `50` | the rest go to the summary |
| `fail-on` | `never` | `block` fails the job on a blocking finding or an incomplete file |
| `model` | the default | |
| `version` | the release this action ships with | |
| `install-from` | none | a pip requirement, to test an unreleased commit |

With `fail-on: never` the job succeeds whatever happens, including provider and GitHub errors,
which become workflow warnings. With `fail-on: block` a blocking finding exits 1 and an error
exits 2.

## Forks

This version supports the `pull_request` event only. A pull request from a fork gets no
secrets and a read-only token, so the action prints a notice and posts nothing. Do not switch
the workflow to `pull_request_target` to get around that: this version refuses it, because
running a model over an outsider's files with your key needs a trust policy that is not built
yet (PB35-p2).

## Cost and time

Each file is a full critique: roughly 30 to 65 seconds and a few hundred thousand tokens for a
30-page document (OI27), and every push repeats it for the files that match. At the 25-file cap
that can be tens of minutes. Narrow `paths`, lower `max-files`, and keep the `concurrency`
block in the example so a new push cancels the run it replaces. These figures have not been
measured on a real pull request (OI32).

## What it does not do

- It posts as `github-actions[bot]` and recognises its own comments by that login. With a personal access token as `github-token` it will repeat comments on every push.

- It does not check out or run anything from the pull request. Files are read over the API at
  the commit the event names.
- It does not resolve or delete old comments.
- It does not judge the author. The summary says what the critics found in the quoted text.
