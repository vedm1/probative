"""`probative github-review` (PROBATIVE_PHASE_SPECS.md PB35): critique the spec files a
pull request changes and post the findings back as a review.

Nothing in this package checks out or runs PR code: files are read over the REST API at
the event's head SHA, and only the pinned `probative` release executes.
"""
