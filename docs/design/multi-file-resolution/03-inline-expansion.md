# Phase 3 — Inline expansion

**Status:** Draft.
**Goal of this phase:** When the evaluator hits an unknown composable
and Phase 2 returns a `ResolvedPath`, parse that file, locate the
named composable's body, and render its top-level calls in the
caller's `Ctx` — as if the body were inlined at the call site. Plumb
results into the existing `_emit` dispatch so the rest of the
evaluator stays untouched.

This is the phase that turns multi-file from infrastructure into
actual coverage. Phases 1 and 2 are plumbing; Phase 3 is the payoff.

---

## Input → Output

**Input (added to the existing `_emit` / `_emit_swift` call):**
- `spec: _CallSpec` (the unknown composable call site, unchanged)
- `ctx: Ctx` (parent layout context, unchanged)
- `resolver: NameResolver | None` — a small thin wrapper around
  `ProjectIndex` + `resolve_name`, plus the **resolution stack** for
  cycle detection. `None` retains v0.1.x single-file behaviour.

**Output:**
- The same `(used_w, used_h)` tuple every other `_render_*` returns.
- Side effect: elements appended to `out`, each carrying the new
  optional `defined_in` field if they came from a resolved body.
- Side effect: `ResolutionStats` accumulator updated.

---

## Algorithm

1. **Guard for missing resolver.** If `resolver is None`, fall back to
   the v0.1.x `ast-unresolved` emission. No behavioural change.
2. **Cycle guard.** Compute the resolution stack
   (set of names currently mid-expansion in this call chain). If
   `spec.name` is already in the stack → emit `ast-unresolved` with
   `reason = "cycle detected: A → B → A"`. Stats: increment
   `cycles_broken`.
3. **Depth guard.** If `len(resolver.stack) >= max_depth` (default 5)
   → emit `ast-unresolved` with `reason = "depth limit reached at
   <Name>"`. Stats: increment `depth_capped`.
4. **Resolve.** `resolved = resolve_name(index, spec.name,
   caller_file=resolver.current_file, platform=platform)`. If `None`:
   emit `ast-unresolved` with the same `"unknown composable: …"`
   reason as today.
5. **Parse the resolved file.** Use the existing `_kotlin_parser()` /
   `_swift_parser()`. Cache parsed trees per file path inside the
   resolver to avoid re-parsing on repeat lookups.
6. **Find the composable body** by name. Re-use
   `_find_composable_body` (Compose) / `_swift_body_statements`
   (SwiftUI) but parametrised by name — both already accept a
   `target` argument.
7. **Push resolver state.** Append `spec.name` to the stack, swap
   `current_file` to the resolved path.
8. **Render the body** via `_iter_top_level_calls` + `_emit` recursion
   (Compose) or `_swift_top_level_calls` + `_emit_swift` (SwiftUI).
   The body's top-level composables render in `ctx` — so the inlined
   children inherit the caller's offset, padding, available extent,
   and `tainted_reasons`.
9. **Pop resolver state** (in `try/finally` to be cycle-safe even on
   exceptions).
10. **Tag emitted elements** with `defined_in = f"{rel_path}:{line}"`
    where `line` is the body's first line in the resolved file.
11. **Stats:** `in_project_composables_resolved += 1`, record
    ambiguity if any.

---

## Worked example — happy path

```kotlin path=ui/SettingsBlock.kt
@Composable
fun SettingsBlock(label: String, modifier: Modifier = Modifier) {
    Row(modifier = modifier.padding(16.dp).fillMaxWidth().height(56.dp)) {
        Text(label, modifier = Modifier.testTag("settings_label"))
    }
}
```

```kotlin path=ui/SettingsScreen.kt
@Composable
fun SettingsScreen() {
    Column {
        SettingsBlock(label = "Account")
        SettingsBlock(label = "Privacy")
    }
}
```

Invocation:

```python
render_compose(
    open("ui/SettingsScreen.kt").read(),
    project_root=Path("ui/").parent,
    screen_width=360,
    screen_height=800,
)
```

Expected elements (modifier forwarding is Phase 4 — for this phase,
Phase 3 ignores the `modifier` parameter; coordinates assume the
default `Modifier`):

```json
[
  {
    "id": "settings_label",
    "role": "text",
    "source": "ast-resolved",
    "x": 16, "y": 16, "w": 0, "h": 20,
    "defined_in": "ui/SettingsBlock.kt:3"
  },
  {
    "id": "settings_label_2",
    "role": "text",
    "source": "ast-resolved",
    "x": 16, "y": 72, "w": 0, "h": 20,
    "defined_in": "ui/SettingsBlock.kt:3"
  }
]
```

Both `Text` elements come back resolved, `defined_in` populated. The
two rows stack at y=0 and y=56 (Row.height 56dp). The `settings_label`
id collision is resolved by appending `_2` to the second occurrence —
the existing `id_counter` already handles this.

---

## Worked example — cycle

```kotlin path=A.kt
@Composable fun Foo() { Bar() }
```

```kotlin path=B.kt
@Composable fun Bar() { Foo() }
```

Invocation: `render_compose(... entry=Foo, project_root=...)`.

Expected: `Foo` resolves, parses, hits `Bar`. `Bar` resolves, parses,
hits `Foo` — but `Foo` is already in the resolution stack. Emit:

```json
{
  "id": "unknown_1",
  "role": "Foo",
  "source": "ast-unresolved",
  "reason": "cycle detected: Foo → Bar → Foo"
}
```

`resolution_stats.cycles_broken == 1`.

---

## Worked example — depth cap

`Foo → Bar → Baz → Qux → Quux → Quuux` — six levels.

At Quuux (depth 6, cap 5), emit:

```json
{
  "id": "unknown_1",
  "role": "Quuux",
  "source": "ast-unresolved",
  "reason": "depth limit reached at Quuux (max 5)"
}
```

The element is not invented; the user sees they hit the cap and can
re-invoke with `max_resolution_depth=10` if their codebase has
genuinely deep nesting. Default stays at 5.

---

## Failure modes

| | Failure | Behaviour |
|---|---|---|
| F1 | Resolved file parses but the named composable is absent (e.g. regex-detected `@Composable` was in a comment) | Same as Phase 2 returning `None` — `ast-unresolved` with reason `"name not found in file: <path>"`. Stats: `false_index_hits += 1`. |
| F2 | Resolved file is unreadable (perms / I/O error) | Emit `ast-unresolved` with reason `"could not read <path>: <error>"`. Do not crash the render. |
| F3 | Resolved body has zero top-level composables (e.g. `fun Foo() { /* empty */ }`) | Returns `(0.0, 0.0)` — no elements emitted, no error. |
| F4 | Resolved body uses local helpers we don't model | Each such call comes back `ast-unresolved` as today. The parent body that resolved is still counted as resolved; the descendant gaps are honest. |

---

## Test strategy

Fixtures under `tests/fixtures/multi_file/expansion/`:

```
expansion_happy/               → SettingsScreen + SettingsBlock (above worked example)
expansion_cycle/               → Foo→Bar→Foo (above)
expansion_depth/               → 6-level chain
expansion_missing_in_file/     → index hit, body absent (regex false positive)
expansion_unreadable_file/     → chmod 000 (set up in fixture script, not committed)
expansion_empty_body/          → @Composable fun Foo() { }
expansion_nested_unresolved/   → resolved body contains unresolved descendant
```

Assertions per fixture:
- Correct elements emitted with `defined_in` populated
- Correct reasons on unresolved elements
- `resolution_stats` matches expected counts
- No exceptions thrown (even on F2)

Cross-platform: every Compose fixture has a SwiftUI mirror under
`expansion_*_swift/`.

---

## Public API changes

```python
# lumo/render/project_index.py

@dataclass
class NameResolver:
    index: ProjectIndex
    platform: Literal["compose", "swiftui"]
    max_depth: int = 5
    stack: list[str] = field(default_factory=list)
    current_file: Path | None = None
    parsed_cache: dict[Path, "Tree"] = field(default_factory=dict)
    stats: "ResolutionStats" = field(default_factory=lambda: ResolutionStats())

@dataclass
class ResolutionStats:
    in_project_composables_resolved: int = 0
    in_project_composables_unresolved: int = 0
    cycles_broken: int = 0
    depth_capped: int = 0
    max_depth_reached: int = 0
    ambiguities: list[dict[str, list[str]]] = field(default_factory=list)
    false_index_hits: int = 0
```

`render_compose` / `render_swiftui` gain `project_root=` and
`max_resolution_depth=` kwargs. The CLI gains `--project-root` and
`--max-resolution-depth`. The MCP tool descriptors gain the same.

`RenderReport.to_dict()` gains `resolution_stats` when a resolver was
used (omitted when `project_root is None` for backward compat).

`Element.to_dict()` adds `defined_in` when present.

---

## Done-when checklist

- [ ] `NameResolver` + `ResolutionStats` exist
- [ ] `_emit` / `_emit_swift` accept an optional resolver, fall back to
      v0.1.x behaviour when `None`
- [ ] Cycle + depth caps work on the fixture chains
- [ ] `defined_in` populates with `rel_path:line` format
- [ ] Existing 249-test suite still passes (regression guard)
- [ ] +15 new tests for Phase 3 (7 happy / cycle / depth / missing /
      empty / unreadable / nested unresolved, × 2 platforms with a
      shared assertion helper)
- [ ] mypy strict clean
- [ ] Re-run dogfood: coverage delta documented in PR description
