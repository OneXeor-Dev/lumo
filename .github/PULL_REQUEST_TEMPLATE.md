<!--
Thanks for the PR. Read CONTRIBUTING.md first if you haven't.
Especially the "What Lumo is NOT" and "Ground rules" sections —
some kinds of contributions are out of scope and we'll close them
fast to save everyone's time.
-->

## What this changes

<!-- One sentence. What ships in this PR. -->

## Why

<!-- One sentence. What problem does it solve, or what user need does it serve. -->

## How it works

<!-- A short paragraph or a few bullets. Skip if obvious from the diff. -->

## Checklist

- [ ] Tests added for the positive case (the check fires when it should).
- [ ] Tests added for the negative case (the check does NOT fire when it shouldn't).
- [ ] `pytest` passes locally (67+ tests).
- [ ] If a new tool: registered as a console script in `tools/pyproject.toml`,
  wrapped in `tools/lumo/mcp/server.py`, listed in
  `installer/src/lib/python.js` `listInstalledBinaries`, and documented
  in `skill/SKILL.md`.
- [ ] If a check uses device-specific constants — output is relative
  (ratio / flag), not absolute (ms). See `tools/lumo/theory/__init__.py`
  for the honesty rule.
- [ ] CHANGELOG.md updated under `## [Unreleased]` (or under the next
  patch version if you know which one).
- [ ] No backend, no network call at runtime. Lumo is local-only in v1.

## Linked issue

<!-- Closes #N. PRs that don't reference an issue may be closed; we discuss scope before code (see CONTRIBUTING.md). -->
