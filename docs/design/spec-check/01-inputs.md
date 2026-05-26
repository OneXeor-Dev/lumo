# 01 — Inputs

[← back to index](./README.md)

Defines everything the tool consumes: CLI shape, env vars, layout
schema, spec format guarantees after source-side flattening.

---

## CLI invocation

```bash
# Confluence
lumo-spec check --layout screen.json \
                --source confluence \
                --page-id 123456789
lumo-spec check --layout screen.json \
                --source confluence \
                --url 'https://acme.atlassian.net/wiki/spaces/MOB/pages/123456789/...'

# Jira
lumo-spec check --layout screen.json \
                --source jira \
                --issue-key CRDES-1234
lumo-spec check --layout screen.json \
                --source jira \
                --url 'https://acme.atlassian.net/browse/CRDES-1234'

# Markdown
lumo-spec check --layout screen.json \
                --source markdown \
                --spec ./prd.md
lumo-spec check --layout screen.json \
                --spec ./prd.md            # source inferred from --spec

# Output controls
... --json                                   # machine-readable
... --out findings.json                      # write to file
... --severity-floor medium                  # drop low-severity findings

# LLM overrides
... --model claude-haiku-4-5-20251001
... --base-url <anthropic-compatible-url>
```

### URL auto-inference

When `--url` is passed without `--source`, the source is inferred:

| URL pattern | Inferred source |
|---|---|
| `*.atlassian.net/wiki/spaces/*/pages/{id}/*` | confluence |
| `*.atlassian.net/browse/{key}` | jira |

Unknown pattern → exit 2 with "could not infer source".

---

## Auth — env vars

Rationale (vs a `lumo config` file): env vars match the OSS pattern
users recognise from `gh`, `aws`, `kubectl`, `terraform`. A config
store would mean writing a secrets-on-disk story (file mode, keyring
fallback, doctor command updates) for zero proven demand. Revisit
in Phase 3 if real users ask.

| Env var | Purpose |
|---|---|
| `LUMO_ANTHROPIC_API_KEY` | Required. Falls back to `ANTHROPIC_API_KEY`. |
| `LUMO_ANTHROPIC_BASE_URL` | Optional. Anthropic-compatible proxy URL (LiteLLM, Bedrock, internal gateway). |
| `LUMO_LLM_MODEL` | Optional. Default: `claude-haiku-4-5-20251001`. |
| `LUMO_JIRA_BASE_URL` | Required for Jira. e.g. `https://acme.atlassian.net`. |
| `LUMO_JIRA_EMAIL` | Required for Jira. |
| `LUMO_JIRA_TOKEN` | Required for Jira. Atlassian API token. |
| `LUMO_CONFLUENCE_BASE_URL` | Required for Confluence. e.g. `https://acme.atlassian.net/wiki`. |
| `LUMO_CONFLUENCE_EMAIL` | Required for Confluence. Defaults to `LUMO_JIRA_EMAIL`. |
| `LUMO_CONFLUENCE_TOKEN` | Required for Confluence. Defaults to `LUMO_JIRA_TOKEN` (same Atlassian token works for both). |

---

## Layout JSON

Standard Lumo layout schema (same one `lumo-theory` and `lumo-parity`
consume). Source label can be anything (`measured`, `ast-resolved`,
`code-estimated`, `description-estimated`) — the spec check doesn't
care how the layout was produced, only what it represents.

---

## Spec format (after source-side flattening)

The spec arrives at the LLM as a single Markdown string with these
guarantees, regardless of source:

- Headings preserved (`# / ## / ###`) so the LLM can anchor evidence.
- Bullet / numbered lists preserved.
- Tables converted to Markdown tables.
- Inline links collapsed to `[text](url)` form.
- Images replaced with `![alt or filename]()` placeholders — the LLM
  cannot see the image; the placeholder flags that visual evidence
  exists but wasn't read.
- Atlassian noise stripped: status macros, panel decoration,
  unfurled link previews, info / warning / note panels are kept as
  blockquotes with a leading tag (`> [INFO] …`).

### Length cap

Hard-capped at **32k characters** in v1. Haiku 4.5 supports more, but
the cap keeps cost predictable and matches what fits comfortably in a
single prompt-cached system message.

If exceeded → fail fast with the actual count and the cap (exit 2).
**Never silent-truncate.** Silent truncation is the worst possible
failure mode for a spec-vs-design check — the user thinks the whole
spec was read.

Workarounds for over-cap specs documented in the error message: split
the page, pass parent only, increase cap via env (Phase 3 if asked).
