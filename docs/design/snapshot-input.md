# Design doc: `snapshot_input` for Lumo Phase 2

**Status:** Draft. No code yet. Open for issues / PRs against this file.
**Date:** 2026-05-17
**Author:** Viktor Savchik

---

## Problem

Lumo's three v0.1 tools (`lumo-theory`, `lumo-parity`, `lumo-wcag`) consume
a layout JSON or a colour pair and return findings. The catch is **where
the layout JSON comes from**. The honesty rule is:

| Source label | Meaning | Trust |
|---|---|---|
| `measured` | real coordinates from a running app or a snapshot test | high |
| `code-estimated` | parsed statically from Compose / SwiftUI source | medium |
| `description-estimated` | inferred from a screenshot / NL prompt | low |

In v0.1, **the user hand-builds the JSON** or has the LLM build it from
code or a screenshot. Both produce `code-estimated` or
`description-estimated` confidence — never `measured`. That ceiling is
the single biggest accuracy gap in the project.

Phase 2 should close it.

## Two roads we already discussed

| Path | Pros | Cons |
|---|---|---|
| AST parsing (Compose / SwiftUI source) | works without running anything | theme tokens, `fillMaxWidth`, dynamic-type, runtime config — all resolve at runtime, so the parser guesses. Same `code-estimated` ceiling as today. |
| Snapshot tests (Paparazzi / `xcodebuild test`) | values are post-rendering, so `measured` is honest | requires the user to have snapshot tests; we need to parse framework-specific output |

Snapshot tests win on accuracy. AST is a fallback for users without snapshot
infrastructure. We start with snapshot tests because it's the path that
unlocks new value, not a worse version of what we already have.

## Android: Roborazzi is the better target

Initial draft of this doc assumed Paparazzi (Cash App) would be the
primary Android backend. After more investigation, **Roborazzi** is a
stronger fit:

| | Paparazzi (Cash App) | Roborazzi (Takahirom) |
|---|---|---|
| Render engine | Layoutlib fork (JVM, no Android runtime) | Robolectric (Android runtime in JVM) |
| View hierarchy access at test time | Limited — Layoutlib does not expose `getLocationOnScreen` reliably | Full — Robolectric runs real `View` code, so coordinates, children, themes all resolve like on a device |
| Theme tokens, `fillMaxWidth`, dynamic type | Resolves to defaults, hard to make match production | Resolves like the real device |
| What we'd ship | A larger capture helper that has to fake Layoutlib's gaps | A small capture helper that just reads the view tree |

So: **Lumo's Android capture library targets Roborazzi first.**
Paparazzi can still be supported, but the helper for it is bigger and
ships later (or as a community contribution). Both frameworks are in
use in the wild — the design must not force a switch — but
documentation and tests assume Roborazzi as the easy path.

This swap doesn't change anything outside the Android side of the
design. The iOS side (`swift-snapshot-testing` / `xcodebuild test`) is
unchanged. The shared layout JSON schema is unchanged. The
`lumo-theory --from` and `lumo-parity --from` CLI flags are unchanged.

## What Paparazzi actually emits (verified, not guessed)

I verified this against `cashapp/paparazzi` source instead of trusting my
prior assumption.

- Default snapshots directory: `src/test/snapshots/` — a tree of **PNG files**.
- Build artefacts: `build/reports/paparazzi/` — **HTML** report plus copies
  of the PNGs, plus delta images on failure.
- Internal Gradle plugin config: `intermediates/paparazzi/<variant>/resources.json`
  — Android resources (string tables, theme indices), **not** layout
  coordinates.

**Paparazzi does not emit a layout JSON.** It renders a Composable to a
bitmap and compares it to the golden bitmap. The view tree exists during
the test run but it is not serialised to disk in any documented format.

This kills the original plan ("parse Paparazzi output → layout JSON").
We need a different approach.

## What `swift-snapshot-testing` actually emits

Same shape: a snapshot **strategy** renders a `UIView` / `SwiftUI.View` to
a PNG or to a text recursion (`.recursiveDescription`). There is no
built-in strategy that emits coordinate JSON.

There is a JSON snapshot strategy, but it targets *Encodable values*, not
layout. Same conclusion as Paparazzi.

## What this means

The honest reframing is:

> **Snapshot frameworks are great test runners but they do not give us
> structured coordinate data out of the box.** To get `measured`
> coordinates we have to do the measurement ourselves *inside* a
> test the user runs.

That changes the design from "parse snapshot artefacts" to "ship a small
helper the user wires into their existing snapshot test, which exports a
JSON next to the PNG."

## Proposed v0.2 design

Two small libraries plus the Lumo tool that consumes their output.

### `lumo-android-capture` (Kotlin, distributed via Maven Central)

A tiny library a developer drops into their Roborazzi test:

```kotlin
@RunWith(AndroidJUnit4::class)
class CartScreenTest {
  @get:Rule val composeRule = createComposeRule()

  @Test fun cart_screen() {
    composeRule.setContent { CartScreen(state) }
    composeRule.onRoot().captureRoboImage("cart_screen.png")
    LumoCapture.dump(
      composeRule.onRoot(),
      to = "build/lumo/cart_screen.json",
    )
  }
}
```

`LumoCapture` walks the rendered semantics tree once (after Compose
has laid it out under Robolectric), extracts `Rect` bounds plus role
hints (semantic role, content description) plus weight hints (if the
user tagged elements with `Modifier.testTag("primary")` or `"nav"`),
and writes a Lumo-schema JSON with `source: "measured"`.

Paparazzi is **also** supported but needs a heavier helper because
Layoutlib does not expose the rendered view tree the way Robolectric
does. v0.2 ships Roborazzi support first; Paparazzi support lands
when there's a contributor who needs it.

### `lumo-ios-capture` (Swift, distributed via SwiftPM)

The symmetric library for SwiftUI / UIKit snapshot tests:

```swift
func test_cart_screen() {
  let view = CartScreen(state: .preview)
  assertSnapshot(of: view, as: .image)
  LumoCapture.dump(view, to: "build/lumo/cart_screen.json")
}
```

Same idea — walk the rendered hierarchy, extract frames in points,
emit Lumo-schema JSON.

### `lumo-theory check --from build/lumo/` (existing CLI, new input mode)

The existing `lumo-theory` and `lumo-parity` CLIs gain a `--from <dir>`
flag that scoops every `*.json` from the directory and runs the existing
checks against each one. The JSON files are the same Lumo schema we
already have — `source: "measured"` because the capture library
guarantees it.

For parity diff specifically: the convention is
`build/lumo/<screen>.android.json` + `build/lumo/<screen>.ios.json` and
`lumo-parity diff --from build/lumo/` pairs them by stem.

## Acceptance criteria for v0.2

The shipped capture libraries must, with no further user code:

1. Produce a Lumo-schema JSON next to every snapshot test invocation.
2. Stamp `source: "measured"` honestly. No silent fallback to
   `code-estimated` when measurement fails — fail loudly instead.
3. Capture `x, y, w, h` in dp (Android) / pt (iOS) — not pixels.
4. Capture `id` from the test tag (`Modifier.testTag` on Compose,
   `accessibilityIdentifier` on iOS) or auto-generate stable IDs from
   the view hierarchy path.
5. Capture `role` heuristics: `primary_action`, `nav_item`, `tab`,
   `icon_button`, `input`, `text`, `image`. Heuristics are good enough
   for v0.2; v0.3 may take explicit annotations.
6. Capture `group` from a sibling-aware container scan (e.g. all direct
   children of a `BottomNavigation` get the same group).
7. **No network**, **no Lumo dependency** at runtime — the captured
   JSON is plain text, validated against the existing schema documented
   in `examples/README.md`.

Tests live in each capture library against a handful of canonical
fixtures (the same screens we use in `examples/`).

## Non-goals for v0.2

- No SwiftUI Preview support (Previews don't always lay out the same
  way as production). v0.2 measures snapshot tests only.
- No screenshot-from-CI capture. The capture library runs locally.
- No AST fallback. That's a separate v0.3+ tool for users who can't
  add a snapshot test.
- No Lumo-side rendering. We're never going to launch a virtual
  Android device.

## Open questions

1. **Test-tag convention.** Should we standardise on
   `Modifier.testTag("primary:btn_continue")` (role:id colon-prefixed)
   or two separate tags? Decision blocks the role-extraction heuristic.
2. **Multi-screen tests.** Some Paparazzi tests render N variants in
   one method. Do we emit one JSON per `paparazzi.snapshot {}` call or
   per `@Test` method? Probably per call.
3. **Where does the capture library live?** Mono-repo (`tools/captures/`)
   or two new repos? Mono-repo simpler; risk is that an Android dev
   has to clone Python tooling to contribute. Lean toward mono-repo
   for v0.2 and split if it becomes a friction point.
4. **iOS scale.** `xcodebuild test` runs on the simulator at 2x or 3x
   depending on device family. The capture library reads `points`
   (already density-independent) and stamps the screen size in points —
   we should *not* emit pixels. Verify on real device simulators with
   different scales before shipping.

## Decision: build order in Phase 2

Original ROADMAP listed `snapshot_input` as Phase 2 tool #5, before
`figma_sync` and `codebase_audit`. This design doc confirms that
ordering for a different reason than the original ROADMAP gave:

- **`snapshot_input` first** (this doc): unlocks `source: "measured"`
  for every existing check. Pure value-add, no rewrite of existing
  tools.
- **`figma_sync` second**: layers on top of measured coordinates —
  diff Figma against the same `source: "measured"` JSON the capture
  library produces.
- **`codebase_audit` third**: the AST tool finally lands, but as a
  *fallback* for users without snapshot tests, not as the primary
  measurement source.

This reorder makes the AST tool's role much smaller: not the source of
truth, just the polyfill.
