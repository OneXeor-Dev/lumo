# Phase 4 — Modifier parameter forwarding

**Status:** Draft.
**Goal of this phase:** When the caller passes a `Modifier` (Compose)
or applies modifiers to a custom view (SwiftUI), forward those
modifiers to the first top-level composable / view inside the
resolved body. This is the hardest sub-phase because it requires
parameter binding across files.

Without Phase 4, multi-file render is functional but inaccurate:
`SettingsBlock(modifier = Modifier.padding(16.dp))` would render with
zero outer padding (the caller's `Modifier.padding(16.dp)` is dropped
on the floor at the function boundary).

---

## Input → Output

**Input:**
- Everything Phase 3 already has, plus:
- `caller_modifier: Modifiers | None` — the parsed Modifier the
  caller passed as the `modifier = ...` argument (Compose) or as a
  chained modifier on the view literal (SwiftUI).
- Resolved body's function / struct definition with parameter list
  visible (already in the tree-sitter tree).

**Output:**
- The inlined body renders with the caller's modifier merged into the
  first top-level composable's own modifier. No new schema fields.

---

## Compose semantics (the rule we implement)

Compose convention, baked into every library composable signature:

```kotlin
@Composable
fun SettingsBlock(modifier: Modifier = Modifier, label: String) {
    Row(modifier = modifier.padding(8.dp).fillMaxWidth()) {  // ← FIRST top-level
        Text(label)
    }
}

// Caller:
SettingsBlock(modifier = Modifier.padding(16.dp), label = "Account")
```

Compose's evaluation: `modifier` parameter is the caller's
`Modifier.padding(16.dp)`. Inside the body, it becomes the receiver
of the chain `.padding(8.dp).fillMaxWidth()`. The first top-level
composable (`Row`) receives the COMPOSED modifier:

```
Modifier.padding(16.dp).padding(8.dp).fillMaxWidth()
```

Effective padding on Row's outer edge: 16 + 8 = 24 (sequential
`.padding(...)` calls accumulate in Compose).

Phase 4 implements this exactly:

1. Parse the resolved function's value parameter list.
2. Find the parameter whose name is `modifier` (convention). If absent
   → no forwarding, render the body as-is (Phase 3 behaviour).
3. When rendering the body, before computing the first top-level
   composable's `Modifiers`:
   a. Identify the chain segment that reads `modifier.<calls>` or
      uses the bare parameter as the receiver.
   b. **Prepend** the caller's modifier transforms to that chain.
4. The rest of the offset-stack math is unchanged.

---

## SwiftUI semantics (asymmetric but possible)

SwiftUI doesn't have a `modifier` parameter. Instead, the caller
chains modifiers on the view literal:

```swift
struct SettingsBlock: View {
    let label: String
    var body: some View {
        HStack {
            Text(label)
        }
        .padding(8)
    }
}

// Caller:
SettingsBlock(label: "Account").padding(16)
```

The caller's `.padding(16)` is applied **outside** the body's
`.padding(8)`. Final outer padding: 16 + 8 = 24 — same shape as
Compose, different syntax surface.

Phase 4 for SwiftUI:

1. Detect that the caller invocation has post-modifiers
   (`.padding(...)`, `.frame(...)`, etc.) — Phase 3 already parses
   these.
2. When rendering the body's first top-level view, **prepend** the
   caller's modifiers to the view's own outer modifiers.
3. Multiple top-level views inside `body` (e.g. a multi-statement
   `body` with `@ViewBuilder`) → caller's modifiers wrap the implicit
   group, which we already render as a `VStack`-like passthrough. The
   modifiers apply to the synthetic stack.

---

## Worked example — Compose

```kotlin path=ui/SettingsBlock.kt
@Composable
fun SettingsBlock(
    modifier: Modifier = Modifier,
    label: String,
) {
    Row(modifier = modifier.padding(8.dp).fillMaxWidth().height(56.dp)) {
        Text(label, modifier = Modifier.testTag("settings_label"))
    }
}
```

```kotlin path=ui/Screen.kt
@Composable
fun Screen() {
    Column {
        SettingsBlock(modifier = Modifier.padding(16.dp), label = "Account")
    }
}
```

Phase 3 (without forwarding): `settings_label` lands at `x=8, y=8`
(only inner 8dp padding; outer 16dp dropped).

Phase 4 (with forwarding): `settings_label` lands at `x=24, y=24`
(16dp outer + 8dp inner). The `Row` itself shows in any nested
debug walk at `x=16, y=16` because the caller's padding is applied
first.

---

## Worked example — SwiftUI

```swift path=ui/SettingsBlock.swift
struct SettingsBlock: View {
    let label: String
    var body: some View {
        HStack {
            Text(label).accessibilityIdentifier("settings_label")
        }
        .padding(8)
    }
}
```

```swift path=ui/Screen.swift
struct Screen: View {
    var body: some View {
        VStack {
            SettingsBlock(label: "Account").padding(16)
        }
    }
}
```

Phase 3: `settings_label` at `x=8, y=8` (inner 8 only).
Phase 4: `settings_label` at `x=24, y=24` (outer 16 + inner 8).

---

## Edge cases

| | Case | Behaviour |
|---|---|---|
| E1 | Resolved function has no `modifier` parameter (Compose) | No forwarding; render as-is. The caller's modifier is silently ignored — that's an honest reflection of "the body cannot accept a modifier". |
| E2 | Multiple top-level composables in body | Compose convention: first one receives the modifier. We follow it. Document explicitly. |
| E3 | `modifier` parameter is renamed (`mod`, `m`, `customModifier`) | We don't second-guess naming. Only the literal name `modifier` triggers forwarding. Document as known limitation. |
| E4 | Caller passes a non-literal modifier (`modifier = someVar`) | We cannot statically evaluate `someVar` — emit `ast-unresolved` for the first top-level child with `reason = "caller modifier is a non-literal expression"`. Honest. |
| E5 | Body's first composable doesn't reference `modifier` at all | Forward the caller's modifier as an OUTER wrap (same as SwiftUI semantics: `.padding(N)` applied to the first child). |
| E6 | Forwarding chain contains a token reference inside the body (`modifier.padding(Theme.spacing.md)`) | The first child becomes `ast-unresolved` per the existing taint rule. The caller's literal modifier transforms still apply to siblings (sibling isolation). |

---

## Honesty rule preserved

Phase 4 strictly preserves the v0.1.x honesty contract:

- If forwarding is unambiguous + every transform is literal → emit
  resolved coordinates.
- If anything is uncertain (E3, E4, E6) → emit `ast-unresolved` for
  the affected element with a specific `reason`. **Never** invent a
  partial coordinate from a guessed transform.

---

## Failure modes

| | Failure | Behaviour |
|---|---|---|
| F1 | Function signature can't be parsed (malformed source) | Skip forwarding; render body without it. Log via stats. |
| F2 | Caller passes `modifier = Modifier` (the bare default) | Treat as empty Modifiers — nothing to forward. Body renders with only its own inner transforms. |
| F3 | Compose function uses `LocalDensity.current` or similar inside a modifier chain | Token-rule applies; first child becomes unresolved with reason. |

---

## Test strategy

Fixtures under `tests/fixtures/multi_file/forwarding/`:

```
forwarding_compose_basic/         → caller passes padding, body has its own
forwarding_compose_default_mod/   → caller omits modifier= → no forwarding
forwarding_compose_renamed_mod/   → param is `mod` not `modifier` → E3 limitation
forwarding_compose_non_literal/   → caller passes `modifier = someVar` → E4 unresolved
forwarding_compose_no_modifier_param/ → body doesn't accept modifier → E1
forwarding_compose_multiple_top_level/ → 2+ top-level composables in body → E2 first-wins
forwarding_swift_basic/           → caller chains .padding on the view literal
forwarding_swift_multiple_outer/  → caller chains 2 modifiers (.padding + .frame)
forwarding_swift_inner_passthrough/ → body has its own .padding inside
```

Each fixture asserts:
- The first emitted element's coordinates reflect both outer and inner
  transforms (or just inner, per case)
- `ast-unresolved` triggers on the documented cases (E3, E4, E6)
- `resolution_stats` does not double-count forwarded composables

---

## Public API impact

Internal only. No new public flags, no new JSON fields beyond what
Phase 3 added. The `defined_in` field already records traceability;
the modifier merging is invisible to downstream consumers.

---

## Done-when checklist

- [ ] Compose modifier parameter detection (`fun X(modifier: Modifier ...)`)
- [ ] Modifier chain prepend logic, sequentially merges multiple
      `.padding(...)` segments correctly
- [ ] SwiftUI outer-modifier wrap (already supported as chained
      modifiers in 0.1.x — Phase 4 just plumbs the caller's chain to
      the first body view)
- [ ] All 9 fixtures pass
- [ ] Existing 249-test suite still passes
- [ ] Re-run 18-screen dogfood after Phase 4: target **≥ 60 %
      coverage** — this is the metric the whole multi-file effort
      is justified by
- [ ] mypy strict clean
- [ ] CHANGELOG entry mentions the honesty rule preservation
      explicitly (especially E3, E4 cases)
