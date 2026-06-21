# 05 — Honesty rules

[← back to index](./README.md)

The seven non-negotiable contracts. Every Lumo tool has an honesty
section; this one is longer because it's the first LLM-backed tool.

---

## 1. Source field is always `"llm-derived"`

Never `"measured"`, never `"ast-resolved"`. The whole tool depends on
an LLM at runtime and pretending otherwise misleads downstream
consumers about confidence level.

## 2. Every finding carries `confidence ∈ {high, medium, low}`

- `high`: direct textual evidence in the spec quote.
- `medium`: inferred from context (spec implies but doesn't state).
- `low`: soft heuristic; model is guessing.

The LLM is instructed to default to `medium` and only emit `high`
when the evidence quote directly states the requirement.

## 3. Every finding carries an `evidence` quote

`evidence` is a verbatim substring of the spec text. **The post-LLM
validator checks substring membership and rejects findings whose
evidence is not present in the fetched spec.**

This guards against the model fabricating quotes — a known LLM
failure mode. Validation happens in pure Python after the LLM call,
not inside the prompt. Belt and suspenders.

Rejected findings drop with a warning printed to stderr ("finding
dropped: fabricated evidence") so users see when this fires.

## 4. No new requirements

The LLM is instructed to surface only what the spec **explicitly or
implicitly requires**. Examples of forbidden findings:

- "Spec doesn't mention dark mode; layout should support it." ❌
- "Best practice is to include error states." ❌
- "Modern apps usually have a back button." ❌

Lumo does not author spec extensions. If a requirement isn't in the
fetched spec, it doesn't exist for the purposes of this check.
Designers and PMs author specs; Lumo audits.

## 5. Model id in output

Every finding records the exact model id used (`claude-haiku-4-5-20251001`,
not a tag like `haiku-latest`). Downstream consumers can filter by
model version and re-run after upgrades. Critical for catching
regressions when Anthropic ships a new model.

## 6. `fetched_at` timestamp

Specs change; the timestamp anchors findings to a specific spec
revision. Format: ISO 8601 UTC.

## 7. No silent truncation of spec text

Length cap exceeded → fail fast with the actual character count and
the cap. Never silently truncate. Silent truncation is the worst
possible failure mode for a spec-vs-design check — the user thinks
the whole spec was read and trusts the findings.

The fail-fast error message includes workarounds (split page, pass
parent only, increase cap via env if added in Phase 3).
