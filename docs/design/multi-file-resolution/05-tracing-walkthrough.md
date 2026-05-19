# Tracing a real request end-to-end

> Borrowed from rust-analyzer's `docs/dev/guide.md` pattern: pick one
> real request, narrate every step. This is the most useful artefact
> for a contributor reading the design for the first time.

We trace `lumo-render compose --file ProfileSettingsScreen.kt
--project-root ~/development/flutter-card-es` — one of the 18 dogfood
screens. Today (v0.1.2) it returns 17% coverage with 5 unresolved
elements; after multi-file ships, the trace below predicts ~85%.

---

## The input

`ui/profile/ProfileSettingsScreen.kt` (excerpt):

```kotlin
@Composable
fun ProfileSettingsScreen(component: ProfileSettingsComponent) {
    val model by component.model.subscribeAsState()
    AppTheme {
        Scaffold(topBar = { TopAppBar(title = { Text("Settings") }) }) { padding ->
            Column(modifier = Modifier.padding(padding).fillMaxSize()) {
                PABannersContent(modifier = Modifier.padding(16.dp))
                SettingsBlock(label = "Account", modifier = Modifier.padding(horizontal = 16.dp))
                SettingsBlock(label = "Privacy", modifier = Modifier.padding(horizontal = 16.dp))
                SettingsBlock(label = "Notifications", modifier = Modifier.padding(horizontal = 16.dp))
                SettingsLogoutBlock(modifier = Modifier.padding(16.dp))
            }
        }
    }
}
```

Five custom composables: `PABannersContent`, `SettingsBlock` (×3),
`SettingsLogoutBlock`. Each lives in another file under `kmp/feature/
private-area/`.

---

## Step 1 — CLI invocation

```bash
lumo-render compose --file ui/profile/ProfileSettingsScreen.kt \
                    --project-root ~/development/flutter-card-es \
                    --screen-width 411 --screen-height 891 \
                    --json
```

`lumo/render/cli.py` parses args, calls
`render_compose(source, project_root=Path("~/development/flutter-card-es"))`.

## Step 2 — Project index (Phase 1)

`build_project_index(root)` walks ~1228 `.kt` files, applies the
shared `DEFAULT_SKIP_DIRS`, regex-scans declarations.

**Output:** `ProjectIndex.compose` contains ~720 entries. Build time
on a warm cache: ~180 ms.

Among them:
- `"PABannersContent" → (kmp/.../PABannersContent.kt,)`
- `"SettingsBlock" → (kmp/.../profile/SettingsBlock.kt,)`
- `"SettingsLogoutBlock" → (kmp/.../profile/SettingsLogoutBlock.kt,)`
- `"AppTheme" → (kmp/.../theme/AppTheme.kt,)`

## Step 3 — Render entry (v0.1.x core, unchanged)

`render_compose` parses the entry source, walks to the body of
`ProfileSettingsScreen`, sets up `Ctx(0, 0, 411, 891)`, starts
`_emit` on the first top-level call: `AppTheme { ... }`.

## Step 4 — Theme passthrough (v0.1.2 behaviour, unchanged)

`AppTheme` matches `_is_theme_wrapper` (suffix `Theme`). It renders
as passthrough: the trailing lambda's children render in the parent
`Ctx` directly. So the chain becomes
`Scaffold { padding -> Column { ... } }` evaluated at origin (0, 0).

## Step 5 — Scaffold + Column (v0.1.2, unchanged)

`Scaffold` matches `SCAFFOLD_LIKE` → renders its trailing lambda's
content as a Column. The `topBar` named-arg lambda is skipped (v1).
The body's `padding` parameter (a `PaddingValues` token) is irrelevant
to layout offset for this evaluator — it would only be visible if we
read its value.

Inside the column at `Ctx(0, 0, 411, 891)`, the first child is
`PABannersContent(modifier = Modifier.padding(16.dp))`.

## Step 6 — UNKNOWN composable triggers resolution (Phase 3 new path)

`PABannersContent` is not a known atom. v0.1.x would emit
`ast-unresolved`. Phase 3 instead:

1. Asks the resolver: `resolve_name(index, "PABannersContent",
   caller_file=ui/profile/ProfileSettingsScreen.kt, platform="compose")`.
2. Phase 2 search order: same-dir → no; parent dir
   `kmp/feature/private-area/` → exactly one candidate. Returns
   `ResolvedPath(path=kmp/.../PABannersContent.kt, ambiguous=())`.
3. Parses `PABannersContent.kt` (cached for the rest of the run).
4. Locates the `@Composable fun PABannersContent` body.
5. Pushes `"PABannersContent"` onto the resolver stack.
6. Renders the body's top-level calls in the current `Ctx`.

## Step 7 — Modifier forwarding (Phase 4 new path)

`PABannersContent` is declared as
`fun PABannersContent(modifier: Modifier = Modifier)`. The body's
first top-level composable is `LazyColumn(modifier = modifier...)`.

Phase 4 prepends the caller's `Modifier.padding(16.dp)` to that
chain. So the `LazyColumn` renders with effective outer padding of
16dp + whatever else the body adds.

Internally, `PABannersContent`'s `LazyColumn` walks each `Banner(...)`
in the body. `Banner` is itself a custom composable — Phase 3
recurses (resolver stack depth = 2).

## Step 8 — Recursive resolution (Phase 3 recursion)

Same flow: `Banner` resolves to `kmp/.../banner/Banner.kt`,
parses, renders. Stack depth = 3.

Inside `Banner`, there's a `Card { Row { ... } }` block plus
inner `Icon` and `Text`. All known atoms. Coordinates land cleanly.

## Step 9 — Honest unresolved deep in the tree

One of `Banner`'s rows uses
`Modifier.padding(MaterialTheme.spacing.md)`. The padding value is a
token — the taint rule kicks in: every descendant of that row comes
back `ast-unresolved` with reason `"padding(MaterialTheme.spacing.md)
is a token"`. Sibling rows stay resolved.

**This is the honesty rule preserved end-to-end through multi-file.**

## Step 10 — Pop, continue, repeat

`Banner` finishes → stack pops to depth 2. `LazyColumn` renders the
next `Banner` → recurse again. After all banners are processed,
`PABannersContent` finishes → stack pops to 1.

Back in `ProfileSettingsScreen`'s Column, the next sibling is
`SettingsBlock(label="Account", modifier=Modifier.padding(horizontal=16.dp))`.
Same pattern: resolve, forward modifier, render body.

## Step 11 — Three SettingsBlock siblings share a resolution cache

The resolver's `parsed_cache` already holds `SettingsBlock.kt`'s
parsed tree from the first call. The next two calls hit the cache —
no extra parse cost. Three id collisions on inner `Text` come back as
`settings_label`, `settings_label_2`, `settings_label_3` thanks to the
existing `id_counter`.

## Step 12 — Final output

```json
{
  "screen": {"width": 411, "height": 891, "unit": "dp"},
  "source": "ast-resolved",
  "elements": [
    {"id": "app_bar_1", "role": "app_bar", "source": "ast-resolved", "x": 0, "y": 0, "w": 411, "h": 64,
     "defined_in": "kmp/feature/private-area/ui/profile/ProfileSettingsScreen.kt:5"},
    {"id": "banner_1", "role": "list_item", "source": "ast-resolved", "x": 16, "y": 80, "w": 379, "h": 88,
     "defined_in": "kmp/.../banner/Banner.kt:12"},
    {"id": "settings_label", "role": "text", "source": "ast-resolved", "x": 16, "y": 192, "w": 0, "h": 20,
     "defined_in": "kmp/.../profile/SettingsBlock.kt:8"},
    {"id": "settings_label_2", "role": "text", "source": "ast-resolved", "x": 16, "y": 248, "w": 0, "h": 20,
     "defined_in": "kmp/.../profile/SettingsBlock.kt:8"},
    ...
  ],
  "resolution_stats": {
    "in_project_composables_resolved": 5,
    "in_project_composables_unresolved": 1,
    "cycles_broken": 0,
    "depth_capped": 0,
    "max_depth_reached": 3,
    "ambiguities": [],
    "false_index_hits": 0
  },
  "coverage": 0.87
}
```

**Predicted coverage on this screen: ~87 %** (vs 17 % today). The
single remaining unresolved is the deep-tree token-padding case from
Step 9 — that's a genuine "we don't know the runtime value" gap, not
a missing-feature gap.

---

## What this trace makes obvious

1. Phase 3 is where the actual user value lands — Phases 1 and 2 are
   plumbing. Allocate review time accordingly.
2. The resolver's parsed-tree cache must be shared across the whole
   render call (Step 11). Without it, three SettingsBlock siblings
   parse the same file three times. Trivial speedup, easy to forget.
3. Honesty rule survives intact (Step 9). Token-tainted subtrees
   still come back unresolved; nothing else changes.
4. `defined_in` is the audit trail. When a user disputes a coordinate,
   they need to know which file's body produced it. Don't drop it.
5. `resolution_stats.ambiguities` should be empty on healthy
   projects. The first time it's non-empty in dogfood is a signal
   we should investigate whether `import`-aware resolution (deferred
   to 0.3.0) is worth pulling in.
