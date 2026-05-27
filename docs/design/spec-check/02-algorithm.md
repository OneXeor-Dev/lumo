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
  (task description + honesty rules + output schema) is fixed across
  all invocations, so it's a cache candidate. Anthropic native cache
  via `cache_control: ephemeral` on the system block; LiteLLM proxies
  pass this through. Actual saving depends on cache hit rate — measure
  during dogfood (Phase 5) rather than quoting a number here.
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

## Model choice — open

Default target is Haiku 4.5 for cost. **Not yet verified** that Haiku
4.5 handles tool-use structured output at this task's complexity
(multi-finding semantic comparison with strict schema). Sonnet 4.6 is
the known-good fallback. The Phase 1 PR resolves this empirically
against the golden cases (see [06-testing.md](./06-testing.md)): if
Haiku's finding quality is acceptable, ship it as default; otherwise
default to Sonnet and document Haiku as the cheap opt-in.

## Cost

Not estimated here — token counts depend on real spec / layout sizes
we haven't measured. The structured output reports input + output
token counts per call so users see actual cost. Measure typical and
worst-case during Phase 5 dogfood, then document ranges in the README
with real numbers. No cost guard in v1.
