# 06 — Testing

[← back to index](./README.md)

How we validate that the tool works and stays working.

---

## Unit tests

- **ADF flattener** (`tools/lumo/spec/adf.py`): ~30 fixtures covering
  paragraphs, headings, lists (bullet + numbered + nested), tables,
  code blocks, panels, status macros, links, mentions, emoji, layout
  sections, images. Each fixture: `input.adf.json` + `expected.md`.
- **Source plugins** (`sources/*.py`): HTTP layer mocked with
  `responses` library. Round-trip fixture ADF → flattened markdown.
- **Markdown plugin**: passthrough + length-cap edge cases.
- **Severity-keyword detector**: table-driven over RFC 2119 wording.
- **Evidence-substring validator**: must reject any finding whose
  `evidence` is not a substring of the spec text. Test with both
  true positives and adversarial fake quotes.

---

## LLM integration tests (replay)

Every LLM-touching test records the request + response to
`tests/fixtures/llm/*.jsonl` once, then replays on CI. Live LLM
calls run only with `LUMO_TEST_LIVE=1`. Pattern borrowed from
`vcr.py` (HTTP cassette idea, applied to LLM API).

This means:
- CI runs are deterministic, fast, no network, no API key needed.
- PR contributors don't need an Anthropic key to run the suite.
- Fixtures are version-controlled — model upgrades that change
  responses surface as visible diffs in PR review.

---

## Golden cases

12 hand-built (spec, layout, expected findings) tuples covering:

| # | Scenario |
|---|---|
| 1 | Missing required element (back button) |
| 2 | Missing required element (CTA) |
| 3 | Missing required state (error state) |
| 4 | Element count mismatch (over) |
| 5 | Element count mismatch (under) |
| 6 | Behavioural constraint — visibility (hide CTA until valid) |
| 7 | Behavioural constraint — ordering (steps in wrong order) |
| 8 | Behavioural constraint — state (loading / disabled) |
| 9 | Copy mismatch (button label) |
| 10 | Spec satisfied — no findings expected |
| 11 | Spec ambiguous — low-confidence finding expected |
| 12 | Spec mentions image-only requirement — `[VISUAL]` placeholder finding |

Each lives under `tests/golden/<n>-<slug>/` with `spec.md`,
`layout.json`, `expected.json`. Reviewing the diff of `expected.json`
across PRs is the primary signal that prompt or model changes affected
behaviour.

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
