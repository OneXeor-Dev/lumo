# 06 — Testing

[← back to index](./README.md)

How we validate that the tool works and stays working.

---

## Unit tests

- **ADF flattener** (`tools/lumo/spec/adf.py`): one fixture per node
  type the flattener handles (paragraphs, headings, nested lists,
  tables, code blocks, panels, status macros, links, mentions, emoji,
  layout sections, images), plus a few composite-document fixtures.
  Each fixture: `input.adf.json` + `expected.md`. Final count follows
  from the node-type set confirmed in Phase 2, not a guess.
- **Source plugins** (`sources/*.py`): HTTP layer mocked (library
  choice deferred with the HTTP client — see [04-sources.md](./04-sources.md)).
  Round-trip fixture ADF → flattened markdown.
- **Markdown plugin**: passthrough + length-cap edge cases.
- **Severity-keyword detector**: table-driven over RFC 2119 wording.
- **Evidence-substring validator**: must reject any finding whose
  `evidence` is not a substring of the spec text. Test with both
  true positives and adversarial fake quotes.

---

## LLM integration tests (replay)

Every LLM-touching test records the request + response to
`tests/fixtures/llm/*.jsonl` once, then replays on CI. Live LLM
calls run only with `LUMO_TEST_LIVE=1`. This is the HTTP-cassette
idea (à la `vcrpy`) applied to the LLM call — needs a small custom
record/replay shim or an existing adapter; pick during Phase 1, this
is a design decision, not an off-the-shelf pattern.

This means:
- CI runs are deterministic, fast, no network, no API key needed.
- PR contributors don't need an Anthropic key to run the suite.
- Fixtures are version-controlled — model upgrades that change
  responses surface as visible diffs in PR review.

---

## Golden cases

Hand-built (spec, layout, expected findings) tuples. The set must
cover, at minimum, every `id` in the finding enum
([03-outputs.md](./03-outputs.md)) crossed with the confidence
levels that matter — plus the must-have negative cases:

- One per finding `id` (missing element, count mismatch, behavioural
  constraint, copy mismatch, extraneous element, ambiguous).
- **Spec satisfied → zero findings** (guards against false positives).
- **Spec ambiguous → low-confidence finding** (not a hard defect).
- **Image-only requirement → `[VISUAL]` placeholder behaviour.**

Exact count falls out of that matrix once the enum is final, not from
a number picked up front. Each lives under `tests/golden/<n>-<slug>/`
with `spec.md`, `layout.json`, `expected.json`. The diff of
`expected.json` across PRs is the primary signal that a prompt or
model change shifted behaviour.

---

## End-to-end dogfood

Gated behind `LUMO_TEST_DOGFOOD=1`. One CRDES, one MMES, one MMMX
ticket per release. Run `lumo-figma render` + `lumo-spec check
--source jira --issue-key …` on each. Compare output across releases
to catch regressions.

Not part of CI — runs locally before tagging a release.

---

## CI

- Default `pytest` run uses replay only. No network. No API key.
- Live run nightly with `LUMO_TEST_LIVE=1` and a project secret
  (Anthropic key) to detect Anthropic-side drift early.
- Live run failure does not block PRs but does open an issue.
