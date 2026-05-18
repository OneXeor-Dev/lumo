---
name: lumo
description: "Mobile UI/UX design intelligence grounded in cognitive science (Fitts, Hick, Gestalt, Nielsen) and platform guidelines (Apple HIG, Material Design). Specialised for Jetpack Compose, Android XML, SwiftUI, and UIKit. Use when: \"WCAG\", \"contrast\", \"accessibility\", \"colour pair\", \"design audit\", \"mobile UI review\", \"Compose vs SwiftUI\", \"Fitts's law\", \"Hick's law\", \"touch target\", \"safe area\"."
---

# Lumo

Mobile design intelligence for Claude Code. Lumo combines a curated rule set
with a small toolkit of deterministic Python tools — so checks that need real
math (WCAG luminance, OKLCH correction, AST diff, cross-platform parity)
return facts, not LLM guesses.

## When to Use

Use Lumo when the user request touches any of:

- Accessibility / WCAG contrast questions on a colour pair or palette
- Reviewing or auditing mobile UI code (Jetpack Compose, Android XML,
  SwiftUI, UIKit)
- Comparing the same screen across iOS and Android for visual / behavioural
  parity (padding, animation timing, touch target, typography scale)
- Applying cognitive-science rules to a layout: Fitts (target size × distance),
  Hick (choice count → decision time), Gestalt grouping, Nielsen heuristics
- Choosing or validating colour tokens for a mobile design system
- Detecting platform-specific anti-patterns (e.g. emoji as system icons,
  hardcoded hex in components, missing safe-area handling)

## When NOT to Use

Skip Lumo entirely for:

- Pure backend / API / database tasks
- Non-mobile web design (use a web-focused skill instead)
- Build / CI / dependency / version-bump tasks
- Performance work that doesn't touch UI rendering
- Tasks where the user has explicitly opted out of design feedback

Do not invoke Lumo "just in case" the request might be design-adjacent.
If the request doesn't match a trigger above and the user hasn't named a
mobile UI concern, stay out.

## Tools

Lumo ships with Python tools. Each tool has a single CLI entry-point with
deterministic output. Invoke via Bash. Tools live in `tools/lumo/<area>/cli.py`
and are exposed as console scripts after `pip install -e tools/` or
`pipx install lumo-mobile`.

When running inside an MCP-aware client (Cursor, Continue, Aider, Goose,
Zed, Codex, or Claude Code with MCP enabled), the same tools are
also exposed as MCP functions: `lumo_wcag_check`, `lumo_wcag_fix`,
`lumo_theory_check`, `lumo_parity_diff`, `lumo_source_check_compose`,
`lumo_source_check_swiftui`, `lumo_audit_scan`, `lumo_figma_diff`.
Prefer the MCP function over spawning a Bash subprocess when available
— the structured response is already JSON and the user does not see
noisy command output.

### `lumo-wcag` — WCAG contrast validator + OKLCH auto-correct

When to invoke:

- The user provides a foreground/background colour pair and asks whether it
  is accessible.
- The user pastes a palette (multiple pairs) and asks to validate it.
- A design audit needs to check colour tokens against WCAG.

Commands:

```bash
# Check a single pair against WCAG (default: AA / normal text)
lumo-wcag check --fg "<hex>" --bg "<hex>" [--level AA|AAA] [--size normal|large]

# Auto-correct a failing pair by adjusting the foreground in OKLCH
# (preserves chroma + hue, so brand identity stays intact)
lumo-wcag fix   --fg "<hex>" --bg "<hex>" [--level AA|AAA] [--size normal|large]

# Add --json to either command for machine-readable output
```

Worked example — checking a Tailwind blue-500 button on white:

```bash
$ lumo-wcag check --fg "#3B82F6" --bg "#FFFFFF" --level AA --size normal
FAIL  #3B82F6 on #FFFFFF  ratio=3.678:1  required=4.5:1  (AA, normal text)
```

Worked example — auto-correcting a sky-300 label on white:

```bash
$ lumo-wcag fix --fg "#7DD3FC" --bg "#FFFFFF" --level AA --size normal
FIXED  #7DD3FC → #1B7BA1  on #FFFFFF
       ratio 1.667:1 → 4.779:1  (required 4.5:1)
       strategy=darken_fg  iterations=14
```

Exit codes: `0` pass / unchanged, `1` check failed, `2` correction unreachable.

### `lumo-theory` — cognitive-science layout checks

When to invoke:

- The user provides a screen layout (as coordinates, as code, or as a
  screenshot you've described) and asks for a design review.
- An audit needs to check Fitts (target difficulty), Hick (choice overload),
  Gestalt proximity, or thumb-reachability of primary actions.

What this tool **does not** do:

- It does not produce absolute Fitts MT or Hick RT in milliseconds.
  Those depend on device-specific constants (a, b) with ±40 % variance
  between studies. We return relative comparisons and discrete flags.
- It does not check Nielsen heuristics — those aren't reliably numeric.
  See "Inline Rules → Nielsen heuristics" below for manual-review guidance.
- It does not invoke any LLM. If the layout JSON was estimated by a model,
  declare that with `"source": "description-estimated"` so findings carry
  the right confidence label.

Command:

```bash
lumo-theory check --layout path/to/layout.json [--json]
```

Layout JSON schema:

```json
{
  "screen":  { "width": 411, "height": 891, "unit": "dp" },
  "source":  "measured | code-estimated | description-estimated",
  "elements": [
    {
      "id": "btn_continue",
      "role": "primary_action",
      "x": 24, "y": 800, "w": 363, "h": 56,
      "group": "form_actions",
      "weight": "primary"
    }
  ]
}
```

- `role` ∈ `primary_action | secondary_action | nav_item | tab |
  list_item | input | icon_button | text | image | decorative`
- `weight` ∈ `primary | secondary | equal` (default `equal`)
- `group` is a free-form string used by Hick (equal-weight overload) and
  Gestalt proximity.
- `source` reports honesty: `measured` means the coordinates came from a
  real device or a snapshot-testing framework — Espresso, XCUITest,
  Compose `onGloballyPositioned`, SwiftUI `GeometryReader`, **Paparazzi**
  (Compose snapshot tests by Cash App / JetBrains), or
  `xcodebuild test --only-testing` with `XCTAttachment` /
  `swift-snapshot-testing`. `code-estimated` means the layout was parsed
  from source code statically (theme tokens, `fillMaxWidth`, dynamic
  type — anything that resolves at runtime — is a guess).
  `description-estimated` means the layout was built from a screenshot
  description or natural-language prompt. The tool propagates this value
  to every finding so the user can weigh confidence.

When you (the model) construct a layout from a screenshot or from Compose
/ SwiftUI source code, set `source` to the matching honest label. Do not
default to `measured` — that would falsely inflate confidence.

Worked example — a deliberately bad screen:

```bash
$ lumo-theory check --layout examples/bad.json
FOUND  3 findings (2 high, 1 medium)
       source: measured

  1. [HIGH    ] fitts_undersized_target
     elements: close
     Element 'close' is 32dp on its shorter side, below the minimum tap
     target (48dp).
     → Increase the touchable area to at least 48dp, either by growing
     the element or by extending the hit area (Compose:
     Modifier.minimumInteractiveComponentSize; SwiftUI: .contentShape;
     UIKit: hitTest override).
     metric: smaller_side=32.00, minimum=48.00
  ...
```

Exit codes: `0` no findings, `1` findings reported.

### `lumo-parity` — cross-platform parity diff

When to invoke:

- The user has the same screen built on Android (Compose / XML) and iOS
  (SwiftUI / UIKit) and wants to know where the two diverge.
- The user has a design system (tokens) and wants to verify both platforms
  match it.

What this tool does:

- Compares two layout JSONs (same schema as `lumo-theory`), one per platform.
- Flags numeric mismatches in size and presence of named elements.
- Whitelists known legitimate platform divergences (Material 48dp vs Apple
  HIG 44pt touch targets, Material bottom nav 80dp vs iOS Tab Bar 49pt) and
  reports them as `info`, not as mismatches.
- Optionally validates both layouts against a shared `lumo.config.json` so
  divergence from the design system is reported as a separate, higher-
  severity finding.

What this tool **does not** do:

- It does not flag position (x, y) mismatches. Different screen widths and
  safe-area insets legitimately shift coordinates; flagging those would be
  noise. Size, presence, and design-system tokens are what matter for parity.
- It does not parse Compose or SwiftUI source code in v1. The model is
  expected to translate code into layout JSON as preprocessing, then call
  the tool. Set `source` to `code-estimated` in that case.

Common bug pattern this tool catches:

A junior dev writes `Modifier.padding(16.dp)` on Android but `.padding(48)`
on SwiftUI, believing iOS uses "3× because Retina". Both `dp` and `pt` are
density-independent and **equal in physical size on screen**. 16 ≠ 48.
`lumo-parity` will flag this immediately.

Command:

```bash
lumo-parity diff \
  --android path/to/android.json \
  --ios     path/to/ios.json \
  [--config path/to/lumo.config.json] \
  [--json]
```

Optional `lumo.config.json` schema:

```json
{
  "spacing": { "sm": 8, "md": 16, "lg": 24 },
  "sizing":  { "primary_button_height": 56 },
  "colors":  { "primary": "brand.primary", "surface": "brand.surface" }
}
```

Worked example — Android card with `padding(16.dp)` paired with SwiftUI
`.padding(48)`:

```bash
$ lumo-parity diff --android examples/parity_android.json --ios examples/parity_ios.json
FOUND  6 parity findings (1 high, 3 medium, 2 info)
  ...
  2. [MEDIUM] height_mismatch
     element: card_offer
     android: 16.0    ios: 48.0
     'card_offer' height differs between platforms: Android 16.0dp vs iOS 48.0pt.
     dp and pt are both density-independent and should match.
  ...
  5. [INFO  ] platform_specific_default
     element: nav_back
     android: 48.0    ios: 44.0
     'nav_back' width differs by design: 48.0dp / 44.0pt.
     Minimum touch target: Material 48dp vs Apple HIG 44pt.
```

Exit codes: `0` parity, `1` mismatches present.

### `lumo-source` — AST-based design-system drift checks (Compose + SwiftUI)

When to invoke:

- The user pastes Compose or SwiftUI source and asks for a code-level
  design review (hardcoded colours, off-scale paddings, undersized
  buttons).
- An audit needs to scan an actual `.kt` / `.swift` file rather than a
  translated layout JSON.
- The user wants to confirm a screen uses theme tokens consistently
  before merging.

What this tool does:

- Parses the source with `tree-sitter-kotlin` or `tree-sitter-swift`
  (deterministic, no LLM).
- **Compose:** walks `Modifier.<call>(…)` chains, `Color(0x…)`
  constructors, and `RoundedCornerShape(…)` declarations.
- **SwiftUI:** walks chained view modifiers (`.frame`, `.padding`,
  `.cornerRadius`) and `Color(red:green:blue:)` constructors.
- Flags four checks per platform (HIG-tuned where relevant):
  - `undersized_tap_target` (a11y, **high**) — `Modifier.size(N.dp)`
    with `N < 48` on Compose; `.frame(width: N, height: N)` with both
    `N < 44` on SwiftUI (Apple HIG minimum).
  - `off_scale_spacing` (consistency, **medium**) — padding not on the
    spacing scale, both platforms.
  - `hardcoded_color` (token, **medium**) — `Color(0xFFRRGGBB)` on
    Compose; `Color(red:green:blue:)` (or `Color(.sRGB, red:..., green:...,
    blue:...)`) with all-numeric channels on SwiftUI.
  - `off_scale_radius` (consistency, **low**) — `RoundedCornerShape(N.dp)`
    on Compose; `.cornerRadius(N)` on SwiftUI.

Honesty rule (locked):

- The tool flags only **hardcoded literals**. Token references like
  `MaterialTheme.spacing.md.dp`, `LocalDimensions.current.iconSize`, or
  `MaterialTheme.colorScheme.primary` are intentionally **not** flagged
  — we cannot resolve the runtime value statically, and these are the
  pattern Lumo wants to encourage, not punish.
- All findings carry `source: "code-estimated"`. The parser is exact,
  but runtime resolution is not, so the confidence label stays honest.

What this tool **does not** do:

- On Compose, it does not check named-arg shapes like
  `Modifier.padding(horizontal = 8.dp, vertical = 16.dp)` or per-corner
  `RoundedCornerShape(topStart = 16.dp, ...)`. Documented limitation.
- On SwiftUI, it does not flag `.cornerRadius` inside
  `.clipShape(RoundedRectangle(cornerRadius:))`; only the top-level
  `.cornerRadius(N)` shape. It does not resolve `Color(hex: "…")` custom
  extensions (treated as tokens — the extension implementation isn't
  known statically).
- It does not flag single-dimension `.frame(width: N)` on SwiftUI —
  ambiguous in isolation (might be inside a fixed-height row). Both
  width and height must be literal AND undersized to flag.
- It does not run a project-wide scan (use the upcoming `lumo-audit`
  for that; this tool is per-file).

Command:

```bash
# Compose — language inferred from the .kt extension
lumo-source check --file path/to/Screen.kt

# SwiftUI — language inferred from the .swift extension
lumo-source check --file path/to/Screen.swift

# Pipe from stdin — language must be set explicitly
lumo-source check --file - --lang kotlin < path/to/Screen.kt
lumo-source check --file - --lang swift  < path/to/Screen.swift

# Override the spacing / radius scale from a custom design system
lumo-source check --file Screen.kt --scale 0,4,8,12,16,24 --radius-scale 0,8,16,24

# Machine-readable output
lumo-source check --file Screen.kt --json
```

Note on units: dp and pt are both density-independent and equal in
physical size on screen. The same `--scale 0,4,8,12,16,…` budget applies
to both platforms. Use a custom scale only if your design system
explicitly differs across platforms.

Worked example — a screen with three drift signals:

```bash
$ lumo-source check --file BadScreen.kt
FOUND  3 findings (1 high, 1 low, 1 medium) in BadScreen.kt
       language: kotlin

  1. [HIGH    ] undersized_tap_target  (a11y)
     BadScreen.kt:7:41
     Modifier.size(20.dp)
     Modifier.size(20.0.dp) is below the Material minimum tap target (48.0dp).
     → Grow the element to at least 48dp, or extend the hit area with
       Modifier.minimumInteractiveComponentSize() while keeping the visual size.

  2. [MEDIUM  ] hardcoded_color  (token)
     BadScreen.kt:9:21
     Color(0xFFAA0000)
     Hardcoded Color(#AA0000) bypasses the design-system colour tokens —
     refactor will be invisible to this call site.
     → Replace with MaterialTheme.colorScheme.<role> so a theme update reaches
       every consumer at once.

  3. [LOW     ] off_scale_radius  (consistency)
     BadScreen.kt:11:21
     RoundedCornerShape(13.dp)
     RoundedCornerShape(13.0.dp) is not on the radius scale (allowed:
     [0.0, 4.0, 8.0, 12.0, 16.0, 24.0, 28.0, 32.0]).
     → Use a value from the radius scale, or define a named Shape in
       MaterialTheme.shapes if this radius is deliberate.
```

Exit codes: `0` clean, `1` findings present.

### `lumo-audit` — whole-repository design-system audit

When to invoke:

- The user asks for a project-wide review ("audit the whole repo",
  "what's the worst drift in this codebase").
- The user wants to discover the *measured* spacing / radius scale of
  their project — what numbers do designers actually use, vs. what the
  config claims.
- Before sprint planning a refactor: which checks fire most often, in
  which modules, in which language.

What this tool does:

- Walks every `.kt` / `.kts` / `.swift` file under `--root`, runs
  `lumo-source` per file, and aggregates findings.
- Also collects every hardcoded numeric literal for padding, radius,
  and size (separately) and surfaces the top frequencies. This answers
  "what is your *measured* scale?" — strictly more useful than "this
  one file violates the configured scale."
- Always skips noisy / generated directories — `.git`, `build`,
  `.gradle`, `node_modules`, `Pods`, `DerivedData`, `dist`, `out`,
  `__pycache__`, `.venv`, `venv`. These are non-negotiable; pass
  `--exclude` for additional project-specific globs.

Honesty rule (same as `lumo-source`):

- Only **hardcoded literals** appear in the scale tables. Token
  references (`MaterialTheme.spacing.md`, `LocalDimensions.current.md`,
  `Theme.spacing.md`) are intentionally invisible to the audit, because
  the audit is about catching drift away from tokens — not against them.

What this tool **does not** do:

- It does not propose changes. It surfaces measured data; the human
  decides what scale to standardise on, what to refactor, what to
  keep as a deliberate exception.
- It does not extract design tokens from `strings.xml` / `Assets.xcassets`
  yet. WCAG checks on resource-defined colours land in a later phase.
- It does not respect `.gitignore` — instead, it has a built-in skip
  list (above) plus user-supplied `--exclude` globs. A `.lumoignore`
  format may land later if there's demand.

Command:

```bash
# Default scan — uses the Material / HIG spacing scale.
lumo-audit scan --root path/to/repo

# With a project-specific config (recommended for ongoing audits).
lumo-audit scan --root . --config lumo.config.json

# Stack additional excludes on top of the always-skipped directories.
lumo-audit scan --root . --exclude "tests/**" --exclude "samples/**"

# Override the spacing / radius scale from the CLI.
lumo-audit scan --root . --scale 0,4,8,12,16,24,32 --radius-scale 0,8,16

# Machine-readable for CI / further processing.
lumo-audit scan --root . --json

# Persist a markdown summary in addition to stdout.
lumo-audit scan --root . --out lumo-audit/report.md
```

Configuration (an `audit:` section inside `lumo.config.json`):

```json
{
  "audit": {
    "spacing_scale": [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 56, 64],
    "radius_scale":  [0, 4, 8, 12, 16, 24, 28, 32],
    "exclude": ["samples/**", "**/generated/**"],
    "top_n_values": 15
  }
}
```

Worked example — running against the bundled `examples/` directory:

```bash
$ lumo-audit scan --root examples
# Lumo audit — /…/examples
- Files scanned: **2**
- By language: 1 kotlin, 1 swift
- Total findings: **6**

## Findings by check
- `hardcoded_color`: 2
- `off_scale_radius`: 2
- `undersized_tap_target`: 2

## Measured scale
### radius — 4 literal occurrences
| value | count |
|---|---|
| 12.0      | 2 |
| 13.0 ⚠   | 2 |

Off-scale values: `13.0` (⚠ above).
```

Exit codes: `0` no findings, `1` findings present.

### `lumo-figma` — diff Figma design tokens against the codebase

When to invoke:

- The user asks whether the code matches Figma ("are we using the
  design system", "what's drifted", "what tokens are missing").
- A design-system handoff happened in Figma and the user wants to see
  which tokens already exist in code and which are still hardcoded.
- After running `lumo-audit`, the user wants to validate the measured
  scale against the canonical design tokens in Figma.

What this tool does:

- Fetches **variables** (the modern Figma token system, 2023+) for a
  given file via `GET /v1/files/{key}/variables/local`. Resolves
  aliases (variable → variable → concrete value), picks a mode per
  collection (default or `--mode <name>`), canonicalises values:
  - COLOR → `#RRGGBB` (alpha dropped; code-side `lumo-audit` doesn't
    carry alpha either).
  - FLOAT → bare float (matches `lumo-audit` scale literals).
  - STRING / BOOLEAN are accepted but not part of the v1 diff.
- Diffs against a `lumo-audit --json` payload. Three buckets:
  - `matched` — token value present in Figma AND in code, with code
    occurrence count.
  - `unused_in_code` — token exists in Figma but no literal in code
    matches its value. Note: theme indirection (`MaterialTheme.*`,
    `LocalDimensions.*`, `Color("brandPrimary")`) is invisible to the
    AST audit, so a token may still be used via the design system
    layer — treat the list as **candidates for review**, never a
    hit-list for deletion.
  - `missing_from_figma` — value used in code ≥ `--missing-threshold`
    times (default 3) with no Figma token. Strong candidate for
    promotion to the design system.

Honesty rules:

- **Match by value, not by name.** Figma names (`spacing/lg`) and code
  identifiers (`Dimens.lg.dp`, `Theme.spacing.large`) drift across
  projects. The only stable join key is the resolved number / hex.
  Names appear in the report for human reference, never as a match key.
- **Alpha is dropped on colours.** Code-side colours don't carry it; if
  we matched on alpha we'd produce false drift for opaque tokens that
  read as `0xFFRRGGBB` in code vs `{r,g,b,a:1}` in Figma.
- **Variables only in v1.** Styles (the older Figma token system) need
  a node-tree walk and ship in a later phase. If the user's design
  system is styles-based, the tool returns an empty fetch — flag this
  explicitly and don't pretend the file is empty.

What this tool **does not** do:

- It does not generate code. No token export, no theme scaffolding —
  Lumo reports drift; you decide how to refactor.
- It does not modify the Figma file. Read-only API calls only.
- It does not compare layout / frame geometry between Figma and code.
  That's the snapshot-input piece in Phase 2.5.

Auth:

- Set `FIGMA_TOKEN` in the environment. Never pass tokens via CLI flags
  — shell history. Generate a personal access token at
  `https://www.figma.com/developers` and export it before running.

Command:

```bash
# Against a saved audit JSON.
lumo-audit scan --root . --json > audit.json
lumo-figma diff --file-key abc123 --audit audit.json

# Or all-in-one (scans the repo inline, faster iteration).
lumo-figma diff --file-key abc123 --root .

# Pick a Figma mode (e.g. Dark).
lumo-figma diff --file-key abc123 --root . --mode Dark

# Raise / lower the missing-from-figma threshold (default: 3 uses).
lumo-figma diff --file-key abc123 --root . --missing-threshold 5

# Pass the URL instead of extracting the file key yourself.
lumo-figma diff --url "https://www.figma.com/design/abc123/My-File" --root .

# Machine-readable for CI / chaining.
lumo-figma diff --file-key abc123 --root . --json
```

Worked example — Figma has `spacing/lg=24`, code has 7 `padding(24.dp)`
plus 5 `padding(13.dp)`:

```bash
$ lumo-figma diff --file-key abc123 --root .
# Lumo ↔ Figma — file abc123 (mode: default)

- Figma tokens fetched: 1 (0 COLOR, 1 FLOAT, …)
- Matched in code: 1
- Unused in code: 0
- Used in code but missing from Figma: 1

## Matched tokens
| Token | Type | Value | Code kind | Code uses |
|---|---|---|---|---|
| `spacing/lg` | FLOAT | `24.0` | padding | 7 |

## Missing from Figma
| Value | Kind | Uses |
|---|---|---|
| `13.0` | padding | 5 |
```

Exit codes: `0` when nothing is missing from Figma, `1` when at least
one value crosses the threshold, `2` on argument / API errors.

## Decision Tree

| User request shape | Action |
|---|---|
| "Is `#ABC123` on `#FFFFFF` accessible?" | `lumo-wcag check` with that pair. |
| "Fix this colour pair." | `lumo-wcag fix`. Report both the corrected hex and the strategy. |
| "Audit this palette." | Run `lumo-wcag check` for every pair in the palette. Summarise as a table. |
| "Review this Compose / SwiftUI screen." | Build a layout JSON (set `source` honestly), then run `lumo-theory check`. Combine with inline rules below for things the tool doesn't cover (typography, animation, anti-patterns). |
| "Is this primary action reachable?" | `lumo-theory check` — the `reach_*` checks cover this. |
| "Are there too many choices on this screen?" | `lumo-theory check` — the `hick_overload` check covers this. |
| "Compare this iOS screen to its Android version." | Build layout JSONs for both platforms (set `source` honestly), then run `lumo-parity diff`. Pass `--config lumo.config.json` when the user has a shared design system. |
| "Does my SwiftUI match the design tokens?" | `lumo-parity diff` with `--config`. Even a single-platform check benefits from design-system validation. |
| "Review this Compose file for design-system drift" / "are there hardcoded colours / off-scale paddings / undersized buttons in this `.kt`?" | `lumo-source check --file <path>`. Don't ask the user to translate the file into a layout JSON first — this tool reads source directly. |
| "Review this SwiftUI file" / "audit this `.swift`" | `lumo-source check --file <path>` (language auto-detected by extension). Apple HIG min tap target = 44pt — Lumo uses that, not the Compose 48dp. |
| "Audit the whole project" / "what is our actual spacing scale" / "where are the drift hotspots" | `lumo-audit scan --root <path>`. Pass `--config lumo.config.json` for project-specific scales / excludes. The measured-scale section answers de-facto scale questions that no per-file tool can. |
| "Does the code match Figma" / "what tokens are missing from the design system" / "is `spacing/lg` actually used" | `lumo-figma diff --file-key <key> --root .` (after `export FIGMA_TOKEN=…`). Matches by value, not name — so a token with a different code name still counts as matched. Treat `unused_in_code` as candidates for review (theme indirection is invisible here), and `missing_from_figma` as promotion candidates. |

## Output Format Contract

When a tool returns results, format the final answer for the user as:

1. **One-line verdict** — `PASS`, `FAIL: <count> issues`, or `FIXED: <change>`.
2. **Issues table** when there are multiple findings, with these columns and
   nothing else:

   | # | Where | Issue | Severity | Fix |
   |---|---|---|---|---|

3. **Tool output** as a fenced block, verbatim. Do not paraphrase ratios or
   hex values — they are facts and must round-trip exactly.
4. **Suggested next step** in one sentence, if and only if there is one.

Do not add closing summaries, emojis, or restatements of the user's request.

## Inline Rules (apply when no tool covers the case)

These are stable rules that the model is expected to apply directly. They
duplicate what `lumo-wcag` and the Phase 2 tools will eventually automate —
keep them here until the tool exists.

### Touch targets

- iOS minimum tap target: **44 × 44 pt**. (Apple HIG, *Designing for iOS*.)
- Android minimum tap target: **48 × 48 dp**. (Material Design *Accessibility*.)
- Minimum gap between adjacent tap targets: **8 dp / 8 pt**.
- Below-minimum icons must extend their hit area (Compose `Modifier.minimumInteractiveComponentSize()`, SwiftUI `.contentShape(Rectangle())` with padding, UIKit `hitTest` override).

### Typography baseline

- Mobile body text: **≥ 16 sp / 16 pt**. Smaller triggers iOS auto-zoom and is below WCAG-recommended legibility.
- Line height for body: **1.4 – 1.6**.
- Always honour the system text-scale (Compose: `TextUnit.sp` not `dp`; SwiftUI: dynamic type styles, not fixed point sizes).

### Animation timing

- Micro-interactions: **150 – 300 ms**.
- Complex transitions: **≤ 400 ms**.
- Exits roughly 60–70 % of enter duration.
- Animate `transform` / `opacity` only — never `width`, `height`, `top`, `left`.

### Safe areas

- Compose: `Modifier.safeDrawingPadding()` / `WindowInsets.safeDrawing`.
- SwiftUI: `.safeAreaInset(edge:)` / `.ignoresSafeArea()` deliberately.
- UIKit: `safeAreaLayoutGuide`, not view bounds.
- XML: `android:fitsSystemWindows="true"` + insets handling, not hardcoded padding.

### Common anti-patterns

| Avoid | Prefer | Why |
|---|---|---|
| Emoji as system icons (`🏠`, `⚙️`) | SVG / vector icon sets (Lucide, Material Symbols, SF Symbols) | Emoji rendering is font-dependent, inconsistent across platforms, untokenisable. |
| Hardcoded hex inside components | Semantic tokens (`MaterialTheme.colorScheme.primary`, `Color("AccentColor")`) | Tokens survive theme switches and dark-mode auditing. |
| Placeholder-only labels | Visible `Text` / `Label` above the field | Placeholder disappears on focus and breaks accessibility. |
| Same components dressed differently per screen | Single styled component reused | Drift kills perceived polish. |
| `if Platform.isIOS` style branching scattered across UI code | Platform-specific files / extensions at the boundary | Prevents accidental "iOS-only" features creeping into Android. |
| Animating `width` / `height` to expand a card | Animate `scale` / `transform`, layout with `AnimatedContent` (Compose) or `matchedGeometryEffect` (SwiftUI) | The former triggers layout reflow each frame — janky on mid-range Android. |
| Hardcoded `padding(16.dp)` everywhere | A `Spacing` token scale (4 / 8 / 12 / 16 / 24 / 32) | Scale rhythm is a baseline polish signal. |

## Self-correction Loops

Apply these in order before answering:

1. **No tool needed?** If the request is conversational ("what's WCAG?"),
   answer directly. Don't invoke `lumo-wcag` for theory questions.
2. **Tool error?** If `lumo-wcag` returns a non-zero exit beyond the
   documented `1` (failed check) or `2` (correction unreachable), surface
   the stderr verbatim and stop. Do not retry blindly.
3. **Zero findings?** Say "no WCAG issues at AA / normal for the pairs you
   provided" — do not invent a finding to look useful.
4. **Many findings (> 10)?** Show the top issues by severity (CRITICAL →
   HIGH → MEDIUM → LOW), then a one-line "+N more" pointer. Do not dump.
5. **Ambiguity?** If the user provided a single colour without saying which
   is foreground and which is background, ask once. Do not guess.

## What Lumo Does NOT Do

- Lumo does not generate screens, mockups, or boilerplate.
- Lumo does not replace a designer's judgement on hierarchy, brand, or copy.
- Lumo does not call any network service. All tools run locally.
- Lumo does not store data anywhere outside the user's working directory.

If the user asks Lumo to do something on this list, say so and stop.
