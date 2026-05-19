# Multi-file AST resolution — design

**Status:** Draft (2026-05-18). No code yet. Open for issues / PRs against this folder.
**Target release:** Lumo `0.2.0`.
**Author:** Viktor Savchik.

---

## TL;DR

`lumo-render` (shipped in `0.1.x`) statically evaluates one Compose
`.kt` or SwiftUI `.swift` file and produces measured-like `(x, y, w, h)`
coordinates. Real-world dogfood on 18 production screens from CRDES /
MMES / MMMX / kmp-common-components topped out at **28.6% coverage**.
The dominant gap: **app-specific custom composables / views defined in
other files** — `SettingsBlockView`, `SmsCodeTimerSection`, `Header`,
`Banner`, etc. The evaluator only reads ONE file, so every reference
to a project-local composable comes back as `ast-unresolved` with
`reason = "unknown composable: <Name>"`.

This RFC introduces **multi-file resolution**: walk the project, build
a `Name → file` index, and when an unknown composable is encountered,
inline its body from the resolving file. The honesty rule (`never
invent coordinates`) is preserved end-to-end — anything we cannot
resolve statically still comes back as `ast-unresolved`.

---

## Non-goals

We declare these BEFORE the goals so scope creep has nowhere to hide.

1. **No library composables.** We do not resolve composables that live
   in Maven artefacts, CocoaPods, or SPM packages. The CRDES /
   kmp-common boundary is exactly where Phase 0.2 stops. Phase 0.3 may
   add `--include-deps` if real users ask.
2. **No runtime evaluation.** No `./gradlew`, no `xcodebuild`, no
   `kotlinc` invocation. Everything stays in the tree-sitter parser.
   The build-based path is reserved for `lumo-build` (Phase 4 — see
   ROADMAP Phase 4 tiered hierarchy).
3. **No conditional bodies.** If a composable's body is
   `if (state) FooView() else BarView()`, we do not enumerate
   branches. The body is still rendered (first branch usually) and the
   honest unresolved entries cover the unknowns.
4. **No symbol-table / type-checker.** We do not implement Kotlin or
   Swift import resolution. We match by the bare composable name. If
   two files declare `@Composable fun Header`, we pick the first by
   path-sort and record an ambiguity warning. Static name collisions
   in mobile codebases are vanishingly rare in practice.
5. **No new layout heuristics.** Multi-file is purely additive plumbing
   — the offset-stack evaluator already handles everything once the
   body is in hand.

## Goals

1. **Resolve in-project custom composables to their source body** at
   render time, then continue evaluation as if the body were inlined.
2. **Same JSON schema as today**, plus one optional field per element:
   `defined_in: "ui/SettingsBlock.kt:42"` so the user can audit which
   elements came from which file.
3. **Preserve every existing honesty rule.** Token references still
   taint descendants. `ast-unresolved` with `reason` is still emitted
   when we can't derive a value. Sibling isolation is preserved.
4. **Opt-in.** Passing `project_root=None` (the current default) keeps
   the v0.1.x single-file behaviour intact. Existing callers don't
   break.
5. **Cross-platform parity.** Compose and SwiftUI ship in the same
   release with symmetric semantics.

## Invariants (locked decisions)

> Borrowed from rust-analyzer's "Architecture Invariants" pattern.
> These are short, numbered statements that stay true forever in this
> design.

1. The evaluator NEVER invents coordinates. Multi-file resolution
   produces either real numbers (because we found a body and walked
   it) OR `ast-unresolved` with a `reason`. There is no third option.
2. The project index is **lazy and per-render**. We do not maintain
   long-lived caches; a fresh `render_compose(..., project_root=…)`
   call walks the project anew. (Callers who want caching hold their
   own `ProjectIndex` instance.)
3. Resolution is **single-pass**. We never re-render a previously
   resolved composable in the same call chain (cycle protection).
4. Depth cap is **5**. Beyond that, the next call site comes back as
   `ast-unresolved` with `reason = "depth limit reached"`. Real
   composable chains are 2–4 deep in practice.
5. The walker is **file-system only**. No network, no IPC, no
   subprocess. `os.walk` + grep-by-regex over `.kt` / `.swift` files.

---

## Phase plan

The work splits into four self-contained PRs, each with its own
sub-doc. Read them in order — each phase has an explicit
**Input → Output** contract that the next phase consumes.

| # | Phase | Sub-doc | Status |
|---|---|---|---|
| 1 | Project index | [01-project-index.md](./01-project-index.md) | Draft |
| 2 | Name resolution | [02-name-resolution.md](./02-name-resolution.md) | Draft |
| 3 | Inline expansion | [03-inline-expansion.md](./03-inline-expansion.md) | Draft |
| 4 | Modifier parameter forwarding | [04-modifier-forwarding.md](./04-modifier-forwarding.md) | Draft |

Plus one walkthrough doc that ties them together with a real
production example:

| | Doc | Purpose |
|---|---|---|
| ★ | [05-tracing-walkthrough.md](./05-tracing-walkthrough.md) | Trace `CRDES-ProfileSettings` end-to-end: from `lumo-render` invocation to final JSON, showing each phase's contribution. |

---

## Public API surface (final shape)

After all four phases ship, the public surface looks like:

```python
# Python
render_compose(
    source: str,
    *,
    target: str | None = None,
    screen_width: float = 360.0,
    screen_height: float = 800.0,
    project_root: str | Path | None = None,   # NEW
    max_resolution_depth: int = 5,            # NEW (rarely overridden)
) -> RenderReport
```

```bash
# CLI
lumo-render compose --file Screen.kt --project-root .
lumo-render swiftui --file Screen.swift --project-root ./ios/
```

```json
// JSON (added optional fields)
{
  "elements": [
    {
      "id": "logout_btn",
      "role": "primary_action",
      "source": "ast-resolved",
      "x": 16, "y": 712, "w": 343, "h": 48,
      "defined_in": "ui/settings/SettingsLogoutBlockView.kt:24"
    }
  ],
  "resolution_stats": {
    "in_project_composables_resolved": 7,
    "in_project_composables_unresolved": 2,
    "max_depth_reached": 3,
    "ambiguities": []
  }
}
```

Everything new is **additive**. Existing consumers of the JSON ignore
extra fields.

---

## Open questions

These remain unresolved at the time of writing. Each should be settled
inside its phase sub-doc before that phase merges.

1. **Should we honour Kotlin `import` statements to narrow the index?**
   Faster + fewer ambiguity warnings, but adds a Kotlin-parser
   responsibility. Settled in [02-name-resolution.md](./02-name-resolution.md).
2. **Modifier forwarding when the callee has multiple top-level
   composables in its body** — apply to first only? to all? Compose
   convention is "first one"; we follow it. Documented in
   [04-modifier-forwarding.md](./04-modifier-forwarding.md).
3. **Resolution stats — top-level or nested per element?** Both: a
   per-element `defined_in` plus a top-level aggregate
   `resolution_stats`. Settled in [03-inline-expansion.md](./03-inline-expansion.md).
4. **SwiftUI dialect of "composable parameter"** — SwiftUI views
   declare `body` and take properties via `init`. Modifier forwarding
   for SwiftUI is structurally different from Compose. Handled
   symmetrically but with platform-specific notes in [04-modifier-forwarding.md](./04-modifier-forwarding.md).

---

## Status / rollout

This RFC is a draft. Each sub-doc is also a draft. We will:

1. Get the design approved (Viktor reviews the four sub-docs).
2. Implement phases 1 → 4 as separate PRs against `main`, each with
   its own test fixtures (see each sub-doc's test section).
3. Re-run the 18-screen dogfood after Phase 4 lands; target ≥ 60%
   coverage. Documented in the 0.2.0 CHANGELOG.
4. Bump to 0.2.0 (minor — new public flag + new JSON fields).
