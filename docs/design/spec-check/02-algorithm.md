# 02 — Algorithm

[← back to index](./README.md)

The pipeline from CLI invocation to emitted findings.

---

## Pipeline

```
1. Parse args. Validate --source / --spec / --url / --page-id / --issue-key combos.
2. Validate env vars for the chosen source.
3. Load layout JSON. Validate against Lumo schema.
4. Fetch spec via source plugin (see 04-sources.md):
     - confluence: GET /wiki/api/v2/pages/{id}?body-format=atlas_doc_format
     - jira:       GET /rest/api/3/issue/{key}?fields=summary,description,comment
     - markdown:   read file
5. Flatten to Markdown (source-specific, see 04-sources.md).
6. Length cap (32k chars). Fail fast if exceeded (no silent truncate).
7. Build LLM prompt:
     - System: task description, honesty rules, output schema (prompt-cached)
     - User:   spec text wrapped in <spec>...</spec> + layout JSON pretty-printed
     - Tool/structured-output: enforce JSON shape via tool use
8. Call LLM (temperature=0, default Haiku 4.5).
9. Parse + validate response against finding schema.
     - On invalid JSON: re-call once.
     - On second failure: exit 2.
10. Evidence-substring validator: reject any finding whose `evidence`
    is not a substring of the fetched spec text.
11. Apply --severity-floor filter.
12. Emit findings (text by default, JSON with --json, file with --out).
13. Exit with appropriate code (see 03-outputs.md).
```

---

## LLM call shape

- **Single message, no conversation.** Spec checks are stateless.
- **`temperature=0`** for reproducibility. Tests rely on this.
- **Prompt caching on the system prompt.** The system message
  (~2-3k tokens of task description + honesty rules + output schema)
  is fixed across all invocations. Cache hit saves ~80 % on system
  tokens. Anthropic native cache via `cache_control: ephemeral` on
  the system block. LiteLLM proxies pass this through.
- **Structured output via tool-use.** Single tool:
  ```python
  tools = [{
      "name": "emit_findings",
      "description": "Emit zero or more spec-vs-layout findings.",
      "input_schema": {<finding schema, see 03-outputs.md>}
  }]
  tool_choice = {"type": "tool", "name": "emit_findings"}
  ```
  Forces valid JSON. Eliminates regex parsing and "the model returned
  markdown around the JSON" failure mode.

---

## Cost (informational)

Haiku 4.5 pricing: ~$1/MTok input, $5/MTok output. Typical check:

| Component | Tokens (approx) |
|---|---|
| System prompt (cached after first call) | 2,500 (cached read: $0.10/MTok) |
| User: spec text | 800 – 4,000 |
| User: layout JSON | 500 – 1,500 |
| Output: findings | 200 – 800 |

Per-check cost (warm cache): ≪ $0.01. Heavy users at 100 checks/day:
< $1. Cold cache (~$0.025 per check) only on the first invocation
per ~5 minutes.

No cost guard in v1 — users see token counts in the structured output
and decide for themselves. Document in README.
