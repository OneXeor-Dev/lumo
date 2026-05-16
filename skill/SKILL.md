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
and are exposed as console scripts after `pip install -e tools/`.

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
  real device (Espresso, XCUITest, Compose `onGloballyPositioned`,
  SwiftUI `GeometryReader`); `code-estimated` from static code parsing;
  `description-estimated` from a description or screenshot. The tool
  propagates this value to every finding so the user can weigh confidence.

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

## Decision Tree

| User request shape | Action |
|---|---|
| "Is `#ABC123` on `#FFFFFF` accessible?" | `lumo-wcag check` with that pair. |
| "Fix this colour pair." | `lumo-wcag fix`. Report both the corrected hex and the strategy. |
| "Audit this palette." | Run `lumo-wcag check` for every pair in the palette. Summarise as a table. |
| "Review this Compose / SwiftUI screen." | Build a layout JSON (set `source` honestly), then run `lumo-theory check`. Combine with inline rules below for things the tool doesn't cover (typography, animation, anti-patterns). |
| "Is this primary action reachable?" | `lumo-theory check` — the `reach_*` checks cover this. |
| "Are there too many choices on this screen?" | `lumo-theory check` — the `hick_overload` check covers this. |
| "Compare this iOS screen to its Android version." | (Tool arrives in Phase 2.) For now, diff manually using the parity rules in `references/parity.md` once it exists. |

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
