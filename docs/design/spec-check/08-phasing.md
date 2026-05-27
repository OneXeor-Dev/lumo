# 08 — Phasing

[← back to index](./README.md)

Per-PR scope and the definition of "0.3.0 ships".

---

## Phase 1 — Markdown source + LLM round-trip

**Branch:** `feat/spec-check-markdown`

Smallest viable slice. End-to-end CLI + LLM call + JSON output +
evidence validator, with the simplest possible source.

**Scope:**
- `tools/lumo/spec/cli.py` — argparse, source dispatch.
- `tools/lumo/spec/sources/markdown.py` — read file, build
  `SpecDocument`.
- `tools/lumo/spec/llm.py` — Anthropic client, prompt builder, tool-use
  call, response parser.
- `tools/lumo/spec/validators.py` — evidence-substring validator,
  schema validator.
- `tools/lumo/spec/output.py` — text + JSON emitters.
- Fixtures: enough markdown spec / layout / expected-findings triples
  to cover at least one finding case and one spec-satisfied (zero
  findings) case end-to-end.

**Doesn't ship:** Confluence, Jira, MCP wrapper.

---

## Phase 2 — Confluence source + ADF flattener

**Branch:** `feat/spec-check-confluence`

**Scope:**
- `tools/lumo/spec/adf.py` — shared ADF → markdown flattener with
  one fixture per handled node type (count follows from the confirmed
  node-type set, see [04-sources.md](./04-sources.md)).
- `tools/lumo/spec/sources/confluence.py` — v2 fetch, v1 fallback.
- `tools/lumo/spec/storage_format.py` — only if Plazo dogfood needs
  v1 fallback.
- HTTP layer mocked via `responses` for tests.

---

## Phase 3 — Jira source

**Branch:** `feat/spec-check-jira`

**Scope:**
- `tools/lumo/spec/sources/jira.py` — fetch issue + comments, assemble
  description + comments markdown per [04-sources.md](./04-sources.md).
- Truncation order tested: oldest comments dropped first; description
  alone over cap fails fast.

---

## Phase 4 — MCP wrapper

**Branch:** `feat/spec-check-mcp`

**Scope:**
- `tools/lumo/mcp/server.py` — add `lumo_spec_check` tool registration.
- `tools/lumo/mcp/wrappers/spec_check.py` — typed wrapper following
  the seven existing tool wrappers' pattern.
- `lumo doctor` — surfaces spec auth env vars in the health check.
- README MCP table updated to 12 functions.

---

## Phase 5 — Dogfood + docs + release

**Branch:** `feat/spec-check-dogfood`

**Scope:**
- One CRDES, one MMES, one MMMX Jira ticket dogfood. Capture output,
  inspect for false positives / negatives, file fixes if needed.
- README "What works today" table includes `lumo-spec`.
- CHANGELOG `[0.3.0]` entry.
- ROADMAP Phase 2 entry #8 (`lumo-spec`) marked ✅ shipped.
- Tag + release v0.3.0.

---

## Deliverable definition — 0.3.0 ships when…

- All five PRs above merged to `main`.
- `lumo-spec check --layout … --spec ./prd.md` works on the example
  fixture without an Atlassian instance.
- `lumo-spec check --layout … --source jira --issue-key CRDES-…`
  works against a real Plazo ticket.
- `lumo-spec check --layout … --source confluence --page-id …`
  works against a real MobileDepartment page.
- MCP tool `lumo_spec_check` registered and visible in `lumo doctor`.
- Pytest suite green with no network access (replay only).
- README "What works today" includes `lumo-spec`.
- CHANGELOG `[0.3.0]` entry written.
- ROADMAP Phase 2 entry #8 marked ✅ shipped.
