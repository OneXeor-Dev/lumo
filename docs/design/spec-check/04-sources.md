# 04 — Sources

[← back to index](./README.md)

Plugin contract + per-source specifics + ADF flattening.

---

## Plugin contract

```python
class SpecSource(Protocol):
    name: str  # "confluence" | "jira" | "markdown"

    def fetch(self, identifier: str) -> SpecDocument: ...

class SpecDocument:
    source_type: str
    source_id: str
    title: str
    markdown: str            # post-flattening, guarantees from 01-inputs.md
    character_count: int
    fetched_at: datetime
    raw_url: str | None      # human-readable link back to the source
```

Plugins live under `tools/lumo/spec/sources/{confluence,jira,markdown}.py`.
Adding a source (Notion, Linear) = new file + registry entry. No core
changes.

---

## Confluence

Uses Atlassian Cloud REST API v2:

```
GET /wiki/api/v2/pages/{id}?body-format=atlas_doc_format
```

The v2 endpoint returns `body.atlas_doc_format.value` as ADF JSON
(string). Parse → flatten via the shared ADF flattener.

### v1 fallback (open question, see 07-risks.md)

v2 may not be GA on every Atlassian instance. Strategy:

1. Try v2 first.
2. On 404 / "endpoint not found", fall back to v1
   (`/wiki/rest/api/content/{id}?expand=body.storage`) which returns
   storage format (XML-ish).
3. Storage-format → markdown converter is a separate module
   (`tools/lumo/spec/storage_format.py`) — bigger surface than ADF,
   port from `~/development/mobile-team-ai-helpers/tools/confluence/`.

### Flattened shape

```markdown
# {page.title}

{body as markdown}
```

Sub-pages NOT followed in v1.

---

## Jira

Uses Atlassian Cloud REST API v3:

```
GET /rest/api/3/issue/{key}?fields=summary,description,comment
```

`description` and each `comment.body` are ADF. Both flow through the
shared ADF flattener.

### Flattened shape

```markdown
# {key}: {summary}

**Type:** {issuetype.name} · **Status:** {status.name}

## Description

{description as markdown}

## Comments

### {comment.author.displayName} — {comment.created}

{comment.body as markdown}

---

### ...
```

Comments included because Plazo (and most teams) refine spec in the
comment thread.

### Truncation order if cap exceeded

1. Trim oldest comments first, one at a time, until under cap.
2. If description alone exceeds cap → fail fast (don't truncate
   description silently).

### Open question: sub-task aggregation

A spec ticket often has `[Flutter]` / `[Android]` / `[iOS]`
sub-tasks with their own descriptions. v1 fetches **parent only**.

Deferred because:
- Multi-ticket aggregation needs a merge strategy (which sub-task
  wins on conflict?).
- Mobile users on Plazo workflow usually have the full spec in the
  parent; sub-tasks add platform-specific notes (those become
  out-of-scope for spec-vs-design).
- Easy to add later as `--include-subtasks` flag.

---

## Markdown

```python
markdown = open(path).read()
title = first H1 heading, or filename
```

No HTTP, no auth. Used for offline / OSS testing and the case where
the spec is checked into the repo (monorepo workflow).

---

## ADF flattening (shared)

Confluence v2 returns ADF. Jira v3 returns ADF for `description` and
`comment.body`. Both flow through one converter at
`tools/lumo/spec/adf.py`.

This is **deliberately a port, not a dependency**, of the logic in
`~/development/mobile-team-ai-helpers/tools/jira/adf.py`. Lumo OSS
cannot depend on a Plazo-internal helper, but the algorithm is
well-tested and worth keeping consistent.

### Coverage

| ADF node type | Markdown output |
|---|---|
| `paragraph` | regular paragraph |
| `heading` (1-6) | `#`-prefix |
| `bulletList` / `orderedList` (nested) | `-` / `1.` with indentation |
| `table` | GFM-style markdown table |
| `codeBlock` | fenced code block with language hint |
| `panel` (info/warning/note/success/error) | blockquote `> [TYPE] …` |
| `status` macro | inline `[STATUS]` |
| `mention` | `@user` (display name) |
| `emoji` | unicode char or `:shortname:` fallback |
| `link` mark | `[text](url)` |
| `text` with marks (strong/em/code/strike) | `**text**`, `*text*`, `` `text` ``, `~~text~~` |
| `mediaSingle` / `media` (image) | `![alt or filename]()` placeholder |
| `layoutSection` / `layoutColumn` | flattened, structure dropped |
| Unknown | comment line `<!-- adf: unknown node "X" -->` |

The "unknown node" comment is intentional — it surfaces gaps in the
flattener instead of silently dropping content.
