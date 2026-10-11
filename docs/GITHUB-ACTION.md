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
| `label` | `probative-review` | `pull_request_target` only: the label a maintainer applies to start a review of an outside author's pull request |
| `model` | the default | |
| `version` | the release this action ships with | |
| `install-from` | none | a pip requirement, to test an unreleased commit |

With `fail-on: never` the job succeeds whatever happens, including provider and GitHub errors,
which become workflow warnings. With `fail-on: block` a blocking finding exits 1 and an error
exits 2.

## Forks and outside authors

With the plain `pull_request` event (the first example), a pull request from a fork gets no
secrets and a read-only token, so the action prints a notice and posts nothing.

To review forks, use [`examples/probative-critique-target.yml`](examples/probative-critique-target.yml),
which uses `pull_request_target`. That event runs with your secrets and a write token on
code you do not control, so the action gates it:

| Who opened the pull request | What starts a review |
|---|---|
| The repository owner, or an org member or collaborator whose permission is write or admin (membership alone is not enough: it can mean read-only) | opened, pushed to, reopened, ready for review, or the `probative-review` label applied |
| Anyone else, including a read-only member | only a maintainer **applying the `probative-review` label** (the person who applied it must have write or admin permission); a later push does not run again, label again |

For an outside author the review covers `.md`, `.markdown` and `.txt` files only. PDF, DOCX
and XLSX files are listed in the summary as skipped and are never downloaded, because their
parsers would run with your model key in the environment. Any other label, a labeler without
write permission, or a failed permission lookup is a notice and nothing else: no model call,
no post.

A refusal is a green check, even with `fail-on: block`: it means "not reviewed", so do not
use this check as a gate for outsiders. The label name is matched exactly (case included),
and anyone who can apply labels can start a review on a trusted author's pull request. A
file over 1 MB from an outside author is skipped. If the pull request moved on since the
event, the run stops with a notice and you apply the label again.

What this does not protect against: **look at the diff before you apply the label.** The
model reads the outsider's text, and a crafted file can skew a verdict (it can still not
call a tool, change a number, or make a quote appear that is not in the file: quotes are
checked against the file's bytes, and bodies are rubric strings plus fenced quotes). The
review reads the commit the label event names; a push after labeling is not reviewed until
the label is applied again.

Never add a checkout step to the `pull_request_target` workflow. The action runs from the
runner's temp directory so a stray `.env` or `uv.toml` could not be read, but nothing else
protects a job that executes pull request code with these secrets.

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
