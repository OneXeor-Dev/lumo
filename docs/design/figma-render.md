# Figma render — design

**Status:** Draft (2026-05-18).
**Target release:** Lumo `0.2.0`.
**Author:** Viktor Savchik.

---

## TL;DR

`lumo-render compose/swiftui` reads code and emits `(x, y, w, h)` with
`source: "ast-resolved"`. Today it cannot answer "**is the design
itself good?**" — the design lives in Figma, not in source code, and
the AST evaluator has nothing to walk.

This RFC adds a third front-end to the render pipeline:
`lumo-figma render --file-key X --node-id Y` hits Figma's REST API,
walks the rendered frame tree, and emits the same Lumo layout JSON
schema — but with `source: "measured"` because Figma gives us the
actual rendered coordinates, not a guess. Downstream
(`lumo-theory check --from`, `lumo-parity diff --from`,
`lumo-wcag`) consume the output unchanged.

This is the missing piece for **design audit without code**: Fitts /
Hick / Gestalt / reach checks on the Figma file directly, before a
single line ships.

---

## Non-goals

1. **No pixel diff** of Figma frame vs rendered app. That's
   `snapshot_input` Phase 3 territory — needs runtime data from
   Roborazzi / swift-snapshot-testing.
2. **No SVG / image export.** We read the layout tree, not the
   bitmap. Figma already serves images via `/v1/images/`; we don't
   replicate that.
3. **No Figma plugin in this phase.** A Figma plugin (UI inside
   Figma's panel) is a separate distribution path; this RFC ships a
   REST-API-backed CLI. If users demand a plugin later (0.3+), we
   ship one — but the REST path covers the core use case today and
   doesn't lock us into Figma's plugin SDK.
4. **No Auto-Layout reconstruction.** Figma exposes
   `absoluteBoundingBox` directly — we don't need to re-run their
   layout engine. (Auto-Layout containers' children also have
   `absoluteBoundingBox` populated post-render.)
5. **No multi-frame batch.** v1 renders one frame at a time. Batch
   mode (`--from <dir-of-node-ids>`) deferred to 0.2.x patch if
   needed.

## Goals

1. **One CLI command** turns a Figma frame URL/ID into a Lumo layout
   JSON. Zero hand-editing.
2. **Output schema identical** to `lumo-render compose/swiftui` so
   `lumo-theory check --from`, `lumo-parity diff --from`, and any
   future tool just work. The only schema difference is
   `source: "measured"` per element.
3. **Honest naming.** When a Figma node's name is `btn_continue`,
   that becomes the element `id`. Frame names like `"Bottom Nav"`
   become `group` hints. The user gets meaningful IDs in downstream
   findings.
4. **Same auth surface as `lumo-figma diff`** — `FIGMA_TOKEN` env,
   never a CLI flag.

---

## Invariants

1. `source: "measured"` on every element. Figma gives us pixel
   coordinates of the rendered frame — that's the highest honesty
   tier we offer. Never downgrade.
2. **One HTTP call per render** (the `/v1/files/{key}/nodes` endpoint
   returns the full subtree). No N+1 round trips, no recursive
   fetching.
3. **No write operations.** Read-only. Figma's REST API does have
   POST endpoints for variables / dev resources; we never call them.
4. **Auth via env, never CLI.** `FIGMA_TOKEN` follows the existing
   `lumo-figma diff` convention; do not break it.

---

## REST API surface

We use **one** endpoint:

```
GET https://api.figma.com/v1/files/{file_key}/nodes?ids={node_id}
Headers:
  X-Figma-Token: $FIGMA_TOKEN
```

Response shape (truncated to the parts we use):

```json
{
  "nodes": {
    "1:23": {
      "document": {
        "id": "1:23",
        "name": "Login Screen",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 411, "height": 891},
        "children": [
          {
            "id": "1:24",
            "name": "Title",
            "type": "TEXT",
            "absoluteBoundingBox": {"x": 24, "y": 80, "width": 363, "height": 32},
            "characters": "Welcome"
          },
          {
            "id": "1:25",
            "name": "btn_continue",
            "type": "INSTANCE",
            "absoluteBoundingBox": {"x": 24, "y": 800, "width": 363, "height": 56}
          }
        ]
      }
    }
  }
}
```

**What we use:**
- `name` → element `id` (slugified if it has spaces).
- `absoluteBoundingBox.x/y/width/height` → x/y/w/h.
- `type` → role heuristic (see below).
- `children` → recursive walk, flatten into top-level `elements` list.
- Frame node → `screen` (root size, root node not in `elements`).

**What we ignore:**
- `fills`, `strokes`, `effects` — visual styling, not layout.
- `constraints` — Figma's responsive rules; we render the absolute
  frame as-is.
- `componentId`, `mainComponent` — Figma component instances; we
  treat as opaque (the tree under them is still walked).

---

## Schema mapping

| Figma | Lumo |
|---|---|
| `node.absoluteBoundingBox.x` (relative to frame) | `element.x` |
| `node.absoluteBoundingBox.y` (relative to frame) | `element.y` |
| `node.absoluteBoundingBox.width` | `element.w` |
| `node.absoluteBoundingBox.height` | `element.h` |
| `node.name` (sanitised) | `element.id` |
| `node.type` + name heuristic | `element.role` |
| frame ancestor name (e.g. "Bottom Nav") | `element.group` |
| top-level frame | `screen` |
| (always) | `element.source = "measured"` |

**Coordinate translation.** `absoluteBoundingBox` is in Figma's
global coordinate space. For Lumo's per-screen layout, we subtract
the frame's `x/y` from every child so the root frame sits at `(0, 0)`.

**Role heuristic** (name-based, applied in order; lowercase exact-
prefix match):
1. `btn_*` or `*Button*` or type=`INSTANCE` + name contains `button` → `primary_action`
2. `nav_*` or frame ancestor name matches `bottom nav|tab bar` → `nav_item`
3. `icon_*` or type=`VECTOR` with square aspect ratio → `icon`
4. `input_*` or `*field*` → `input`
5. type=`TEXT` → `text`
6. type=`RECTANGLE`/`VECTOR` → `image`
7. otherwise → `decorative` (matches existing layout schema enum)

This is deliberately simple — the user can override by renaming layers
to match the convention. Document explicitly in SKILL.md.

---

## Worked example

```bash
export FIGMA_TOKEN=figd_…

# Render a Figma frame to layout JSON
lumo-figma render \
  --file-key abc123XYZ \
  --node-id 1:23 \
  --out login.figma.json

# Run cognitive-science checks on it
lumo-theory check --layout login.figma.json
```

Expected `login.figma.json`:

```json
{
  "screen": {"width": 411, "height": 891, "unit": "dp"},
  "source": "measured",
  "elements": [
    {"id": "title",        "role": "text",           "source": "measured",
     "x": 24, "y": 80,  "w": 363, "h": 32},
    {"id": "btn_continue", "role": "primary_action", "source": "measured",
     "x": 24, "y": 800, "w": 363, "h": 56}
  ]
}
```

`lumo-theory` then runs Fitts/Hick/Gestalt on real Figma coordinates
without anyone hand-building a JSON.

---

## CLI surface

```bash
# Bare render with frame ID
lumo-figma render --file-key abc123 --node-id 1:23

# From Figma URL (parse file-key + node-id automatically)
lumo-figma render --url "https://figma.com/file/abc123/...?node-id=1-23"

# JSON to stdout
lumo-figma render --file-key abc123 --node-id 1:23 --json

# Save to file
lumo-figma render --file-key abc123 --node-id 1:23 --out login.json

# Override screen size (Figma may have non-mobile frame; clamp for theory checks)
lumo-figma render --file-key abc123 --node-id 1:23 --screen-width 411 --screen-height 891
```

`--screen-width/--screen-height` are optional clamps: by default we
take the frame's own `width`/`height` as the screen. Override when
the Figma frame is not at production resolution.

---

## Public API

```python
# lumo/figma/core.py (extended)

def fetch_node_layout(
    file_key: str,
    node_id: str,
    *,
    token: str | None = None,
    screen_width: float | None = None,
    screen_height: float | None = None,
) -> RenderReport:
    """Hit Figma's /v1/files/{file_key}/nodes?ids={node_id} endpoint,
    walk the returned tree, return a RenderReport with source=measured."""

def parse_figma_url(url: str) -> tuple[str, str]:
    """Extract (file_key, node_id) from a Figma URL. Useful for `--url`."""
```

`RenderReport` re-used from `lumo.render.core` — no schema fork. The
`elements` are constructed via the same `Element` dataclass.

---

## MCP wrapper

```python
@server.tool()
def lumo_figma_render(
    file_key: str,
    node_id: str,
    screen_width: float | None = None,
    screen_height: float | None = None,
) -> dict[str, Any]:
    """Render a Figma frame to a Lumo layout JSON."""
```

Brings MCP tool count to **11** (was 10 after `lumo_render_swiftui`).

---

## Failure modes

| | Failure | Behaviour |
|---|---|---|
| F1 | `FIGMA_TOKEN` not set | Raise with clear message (same as `figma diff`). |
| F2 | 401 / 403 from Figma | Raise `FigmaApiError` with the response body. |
| F3 | `file_key` or `node_id` invalid | Figma returns 404; raise with the original message. |
| F4 | Node has no `children` (a leaf) | Emit just the root element with the node's bounding box. |
| F5 | Node has `visible: false` | Skip it. Hidden layers don't render in production. |
| F6 | `absoluteBoundingBox` is `null` (auto-layout placeholder before measurement) | Skip the element AND its children. Surface as `node_skipped` in resolution_stats. Honest. |
| F7 | Very deep tree (>100 levels) | Walk depth-capped at 200; surface `truncated` flag in stats. |

---

## Test strategy

Saved fixtures under `tests/fixtures/figma_render/`:

```
figma_render_basic/
├── api_response.json        ← saved real /v1/files/.../nodes response
└── expected_layout.json     ← hand-verified expected Lumo layout

figma_render_nested_groups/  ← frames within frames, group hints
figma_render_hidden_layer/   ← visible:false → skipped
figma_render_no_bbox/        ← null absoluteBoundingBox → F6 behaviour
figma_render_url_parsing/    ← URL → (file_key, node_id) round-trips
```

Mock the HTTP layer (`httpx`) with the fixture JSON. Assert:
- Element count + coordinates match expected_layout.json exactly
- `source: "measured"` on every element
- Role heuristics produce expected labels
- Hidden / null-bbox handling matches F5/F6

**No live API calls in CI.** The fixtures were captured once
manually; commit them.

---

## Honesty rules summary

- `source: "measured"` is correct here — Figma's `absoluteBoundingBox`
  is the **rendered** coordinate after Auto-Layout / Constraints /
  responsive rules resolve. This IS measurement, not a guess.
- We do NOT compose Figma + code. This tool answers "is the design
  good", not "does the code match the design". The latter is
  `snapshot_input` Phase 3.
- Role heuristics are best-effort. We document the rules so the user
  can name their layers accordingly.

---

## Rollout

1. `0.2.0` ships `lumo-figma render` + MCP wrapper + docs +
   release-checklist pass.
2. SKILL.md gains `### lumo-figma render` section between `lumo-figma`
   (diff) and `lumo-audit`, plus a Decision Tree row.
3. README tool table gains a row.
4. Multi-file AST (the original 0.2.0 plan) shifts to **0.3.0** —
   design doc already exists at
   `docs/design/multi-file-resolution/`. No work lost.

---

## Done-when

- [ ] `fetch_node_layout` works on the saved fixture
- [ ] `parse_figma_url` round-trips common URL shapes
- [ ] CLI `lumo-figma render` produces JSON identical to fixture
- [ ] MCP `lumo_figma_render` wrapper-parity test passes
- [ ] SKILL.md / README / ROADMAP updated
- [ ] CHANGELOG 0.2.0 entry
- [ ] CI green, tag `v0.2.0` pushed
