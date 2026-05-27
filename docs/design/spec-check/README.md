# Spec check — design

**Status:** Draft (2026-05-26). No code yet. Open for issues / PRs against this folder.
**Target release:** Lumo `0.3.0`.
**Author:** Viktor Savchik.

---

## TL;DR

Today Lumo answers "is this design well-built?" (`lumo-theory`), "do
tokens match?" (`lumo-figma diff`), and "does the code match the
design tokens?" (`lumo-source`, `lumo-audit`). It cannot answer
**"does the design match the product requirements?"**.

`lumo-spec check` closes that gap. It pulls a specification from
Confluence, Jira, or local Markdown, pairs it with a Lumo layout
JSON (from `lumo-figma render` or `lumo-render`), and runs an
LLM-backed semantic check. Output is the standard Lumo finding
shape — plus a `confidence` field (`high | medium | low`) and an
`evidence` quote that anchors each finding to the spec text.

This is the first Lumo tool that depends on an LLM at runtime.
The honesty contract makes that explicit: source field is always
`"llm-derived"`, never `"measured"` or `"ast-resolved"`.

---

## Non-goals

We declare these BEFORE the goals so scope creep has nowhere to hide.

1. **No write-back to the spec source.** Read-only.
2. **No spec authoring or templating.** Teams write specs how they
   already do; Lumo reads what's there.
3. **No multi-page consolidation in v1.** One spec source per check.
4. **No Notion / Linear in v1.** Atlassian + Markdown only.
5. **No design generation.** `lumo-spec` reports gaps; designers fix.
6. **No LLM provider lock-in.** Defaults to Anthropic (Haiku 4.5)
   but accepts any Anthropic-compatible base URL.
7. **No spec ↔ code diff.** Lumo compares **spec ↔ layout**.
   Spec ↔ shipped-code holds transitively via `lumo-source`.

## Goals

1. **Read-only semantic comparison** between spec doc and Lumo layout JSON.
2. **Pluggable sources**: Confluence + Jira + Markdown in v1; new
   sources are a single new plugin file.
3. **Honest output**: every finding carries `confidence` and `evidence`
   (verbatim spec quote, validated as substring of the spec text).
4. **Same finding shape as the rest of Lumo** — drops into existing
   tooling, MCP wrappers, annotated PNG output.
5. **Deterministic-enough for tests**: `temperature=0`, structured
   tool-use output, fixture-based replay testing.
6. **Cheap by default**: Haiku 4.5, prompt caching where supported.
7. **Works offline for Markdown** — OSS contributors test without
   an Atlassian instance.

## Invariants (locked decisions)

> Borrowed from the [multi-file-resolution RFC](../multi-file-resolution/README.md)
> pattern. These stay true forever.

1. Source field on every finding is **always** `"llm-derived"`. Never
   `"measured"`, never `"ast-resolved"`.
2. Every finding carries `confidence ∈ {high, medium, low}` and a
   verbatim `evidence` quote.
3. The post-LLM validator rejects any finding whose `evidence` is not
   a substring of the fetched spec text. This guards against quote
   fabrication, a known LLM failure mode.
4. The LLM never authors new requirements. "The spec doesn't mention
   dark mode; layout should support it" is a forbidden finding.
5. `temperature=0` for reproducibility. Tests use replay fixtures,
   not live network.
6. Spec text length is hard-capped (32k chars in v1). Cap exceeded →
   fail fast. **No silent truncation, ever.**
7. Every finding records the exact model id used. Model drift is
   visible, not silent.

---

## Phase plan

Five self-contained PRs, each with its own scope. Read them in order.

| # | Phase | PR branch | Status |
|---|---|---|---|
| 1 | Markdown source + LLM round-trip | `feat/spec-check-markdown` | Draft |
| 2 | Confluence source + ADF flattener | `feat/spec-check-confluence` | Draft |
| 3 | Jira source (description + comments) | `feat/spec-check-jira` | Draft |
| 4 | MCP wrapper + doctor integration | `feat/spec-check-mcp` | Draft |
| 5 | Plazo dogfood + golden cases + docs | `feat/spec-check-dogfood` | Draft |

Each ships as a `0.2.x` patch toward `0.3.0`. Detailed phasing in
[08-phasing.md](./08-phasing.md).

---

## Sub-docs

Read these in the order listed. Each has an explicit **Input / Output**
contract that the next consumes.

| # | Doc | Purpose |
|---|---|---|
| 1 | [01-inputs.md](./01-inputs.md) | CLI shape, env vars, layout JSON, spec format guarantees |
| 2 | [02-algorithm.md](./02-algorithm.md) | Pipeline (fetch → flatten → cap → prompt → call → validate → emit), LLM call shape |
| 3 | [03-outputs.md](./03-outputs.md) | Finding shape, severity derivation, exit codes |
| 4 | [04-sources.md](./04-sources.md) | Plugin contract, Confluence / Jira / Markdown specifics, ADF flattening |
| 5 | [05-honesty.md](./05-honesty.md) | Seven non-negotiable honesty rules — the contract |
| 6 | [06-testing.md](./06-testing.md) | Unit / replay / dogfood / CI strategy |
| 7 | [07-risks.md](./07-risks.md) | Risks, mitigations, open questions |
| 8 | [08-phasing.md](./08-phasing.md) | Per-PR scope and deliverable definition |

---

## Public surface (final shape)

After all five phases ship:

```bash
# Sources
lumo-spec check --layout screen.json --source confluence --page-id 123456789
lumo-spec check --layout screen.json --source jira --issue-key CRDES-1234
lumo-spec check --layout screen.json --spec ./prd.md
lumo-spec check --layout screen.json --url '<atlassian-url>'   # auto-infer source

# Output
... --json                                # machine-readable
... --out findings.json                   # write to file
... --severity-floor medium               # drop low-severity

# LLM overrides
... --model claude-haiku-4-5-20251001
... --base-url <anthropic-compatible-url>
```

MCP exposure: one new tool, `lumo_spec_check`. Same wrapper pattern
as the seven existing MCP tools.

---

## Open questions

Resolved in the sub-docs as referenced.

1. **Confluence v1 vs v2 API.** Detect-and-fallback strategy. See
   [04-sources.md](./04-sources.md).
2. **Image placeholder strategy.** Specs contain inline mockups
   invisible to a text LLM. v1 emits `[VISUAL]` placeholder + lowers
   confidence on adjacent findings. See [07-risks.md](./07-risks.md).
3. **Spec caching on disk.** Deferred to Phase 3 if real users
   complain about Atlassian latency. See [07-risks.md](./07-risks.md).
4. **Jira sub-task aggregation.** v1 fetches parent only. See
   [04-sources.md](./04-sources.md).

---

## What this doc does NOT claim

This is a design doc written before any code. It deliberately does
**not** quote numbers we haven't measured:

- **Default model** (Haiku 4.5 vs Sonnet 4.6) — resolved empirically
  in Phase 1 against golden cases, not assumed.
- **Per-call cost / token counts** — measured during Phase 5 dogfood.
- **Spec length cap** — derived from model context + real Plazo spec
  sizes, not a round number.
- **Fixture / golden-case counts** — fall out of the node-type set and
  the finding-id enum, confirmed during implementation.
- **HTTP client + LLM replay shim** — picked in their phases.

Where a value is TBD, the sub-doc says so explicitly. Decisions
(auth model, honesty contract, source-plugin shape, phasing) are
firm; quantities are not.

## Status / rollout

1. Get the design approved (Viktor reviews this README + sub-docs).
2. Implement phases 1 → 5 as separate PRs, each with fixtures.
3. Dogfood: one CRDES, one MMES, one MMMX ticket per release after
   Phase 5 lands.
4. Bump to 0.3.0 (minor — new public CLI, new MCP tool).
