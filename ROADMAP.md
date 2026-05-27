# Lumo Roadmap

This document is the source of truth for what Lumo is, what it isn't, and the order of work.

---

## Foundation (locked decisions)

These are settled. Do not re-litigate without strong cause.

- **Platforms v1:** Android (Jetpack Compose + XML), iOS (SwiftUI + UIKit)
- **Distribution:** npm CLI installer (`npx @onexeor/lumo init` — top-level `lumo` was taken on npm by a WebGL library), zero backend
- **Positioning:** cognitive-science-driven, not style-guide-driven
- **Storage:** local only (LanceDB or sqlite-vec for embeddings; JSON/CSV for rules)
- **Embedding model:** local (bge-small-en-v1.5, lazy download on first use)
- **License:** MIT
- **Hero feature:** theory-of-design checks (Fitts / Hick / Gestalt / Nielsen)
- **No backend in v1:** no telemetry, no cross-user learning, no cloud sync

## Resolved decisions

- Tools language: **Python** (settled). Reason: AST parsing for Compose / SwiftUI in Phase 2 needs `tree-sitter` and OKLCH math needs `numpy`. npm wrapper installs Python deps under the hood, same pattern as ruff / black / pyright.
- GitHub org: **OneXeor** (settled).

## Resolved post-launch

- **npm package name:** `@onexeor/lumo`. Top-level `lumo` was taken on
  the npm registry by an unrelated WebGL library — the scoped name is
  permanent.
- **PyPI package name:** `lumo-mobile`. `lumo` on PyPI is also taken.
- **Version sync:** PyPI `lumo-mobile` and npm `@onexeor/lumo` are
  bumped together to the same number on every release, even when only
  one side changes code. Locked since v0.0.6.

---

## Prompt Engineering Principles (locked, applies to every skill / sub-skill)

Derived from an analysis of `material-3-skill`, `apple-skills`,
`ui-ux-pro-max-skill`, and `mobile-app-ui-design` — what worked vs. what
clearly didn't. Each new tool integration must satisfy every item below
before merging.

**Frontmatter**

- `description` is one paragraph, ≤ 500 chars, ending with an explicit
  literal-quoted trigger list: `Use when: "...", "...", "..."`.
- No trigger desperation ("even if user just says X" is banned).

**Activation contract**

- Explicit `## When to Use` section with concrete request shapes.
- Explicit `## When NOT to Use` section with skip conditions. Mandatory —
  most failing skills omit this.

**Tools**

- Each tool documented with: purpose, when-to-invoke, full CLI signature,
  at least one worked example with real output, exit-code legend.
- The tool description *is* the example. The model invokes correctly when
  the SKILL.md shows the exact command and the expected output.

**Routing**

- `## Decision Tree` as a 2-column table (`request shape → action`). Tables
  outperform prose for routing.

**Output**

- `## Output Format Contract` section. Specify the exact response shape:
  verdict line, optional issues table (columns enumerated), tool output as a
  fenced block, optional one-sentence next step. Forbid emojis, closing
  summaries, and restatements.

**Anti-patterns**

- Listed as a `Avoid → Prefer → Why` table, not prose adjectives. Borrowed
  from `guide-swiftui-view-refactor` — verb-precise wins.

**Self-correction**

- `## Self-correction Loops` enumerates: "no tool needed", "tool error",
  "zero findings", "too many findings", "ambiguity". Each with a one-line
  rule.

**Scope ceiling**

- `## What Lumo Does NOT Do` lists capabilities explicitly out-of-scope so
  the model declines instead of hallucinating.

**Structure**

- Monolithic `SKILL.md` while total content is under ~600 lines.
- Once content exceeds that or there are ≥ 5 distinct sub-tasks, split into
  `references/<topic>.md` and have the SKILL.md route to them by name.
  (Pattern from `material-3-skill`; the anti-pattern from `ios-liquid-glass`
  is having 17 reference files that the SKILL.md never points to.)

---

---

## Phase 1 — MVP (target: v0.1)

Goal: `npx @onexeor/lumo init` works end-to-end with four demonstrable tools (wcag, theory, parity, mcp) and five install paths (npx installer, skills.sh, Claude marketplace, pipx, git clone).

### Tools

| # | Tool | Status | Notes |
|---|------|--------|-------|
| 1 | `wcag_validator` | ✅ Shipped | W3C luminance formula + OKLCH auto-correct that preserves chroma and hue. 28 tests against WebAIM / Material / Apple anchors. |
| 2 | `theory_check` | ✅ Shipped | Fitts (undersized + relative difficulty for primary), Hick overload, Gestalt proximity (v0.2.1 nested-container skip), reach rules, color contrast (v0.2.2, AA/AAA via lumo-wcag, text-only). Nielsen heuristics intentionally not in the tool (not reliably numeric). |
| 3 | `platform_parity` | ✅ Shipped | Android (dp) vs iOS (pt) diff. Component presence, sizing diff, design-system token validation. Platform-specific defaults whitelisted (44 pt vs 48 dp etc.). 14 tests. |
| 4 | `mcp_server` | ✅ Shipped | Stdio MCP server (`lumo-mcp`) exposing every Lumo tool to Claude Code, Cursor, Continue, Aider, Goose, Zed, Codex. As of v0.0.8 it registers 8 functions (`lumo_wcag_check`, `lumo_wcag_fix`, `lumo_theory_check`, `lumo_parity_diff`, `lumo_source_check_compose`, `lumo_source_check_swiftui`, `lumo_audit_scan`, `lumo_figma_diff`) with registration + wrapper-parity tests for each. |

### Distribution (five install paths, all wired up)

| # | Path | Status | Notes |
|---|------|--------|-------|
| 1 | `npx @onexeor/lumo init` | ✅ Published | Custom Node installer, 4 supported AI clients (Claude, Cursor, Codex, generic). Live on npm as [@onexeor/lumo](https://www.npmjs.com/package/@onexeor/lumo). |
| 2 | `npx skills add OneXeor-Dev/lumo` | ✅ Shipped | `skills.json` manifest at repo root for vercel-labs/skills (skills.sh ecosystem). |
| 3 | `claude plugin marketplace add OneXeor-Dev/lumo` | ✅ Shipped | `.claude-plugin/marketplace.json` + `plugin.json` following the apple-skills schema. |
| 4 | `pipx install lumo-mobile` | ✅ Published | Live on PyPI as [lumo-mobile](https://pypi.org/project/lumo-mobile/). |
| 5 | Git clone + manual copy | ✅ Shipped | Documented in README as the zero-installer fallback. |

### Data (ships with the package)

Rules are currently inline in each tool — adequate while the rule count is
small. They will move to `data/` once a second consumer (Phase 2 audit)
needs to read them.

### Skill structure (current)

```
lumo/
├── README.md             # user-facing
├── ROADMAP.md            # this file
├── CHANGELOG.md          # release notes (PyPI + npm)
├── skill/
│   └── SKILL.md          # main Claude Code entrypoint
├── tools/
│   ├── pyproject.toml
│   └── lumo/
│       ├── wcag/         # ✅ tool 1
│       ├── theory/       # ✅ tool 2
│       ├── parity/       # ✅ tool 3
│       ├── source/       # ✅ tool 4 — Compose + SwiftUI AST checks
│       ├── audit/        # ✅ tool 5 — whole-repo aggregator
│       ├── figma/        # ✅ tool 6 — Figma token diff
│       └── mcp/          # ✅ MCP server (8 functions)
├── data/                 # placeholder — rules still inline
├── examples/             # ✅ layout pairs + .kt / .swift anchors + lumo.config.json
└── installer/            # ✅ @onexeor/lumo on npm
```

---

## Phase 2 — Differentiators (v0.2–0.5)

**Priority shift (2026-05-25):** the original Phase 2 order optimised for
coverage depth (multi-file resolution first, lumo-spec last). After
revisiting the success criteria — *"Lumo should tell me in detail why a
design fails Tier 1, and whether the code matches the design"* — we
reordered around the two categories Lumo doesn't cover at all yet
(requirements check, polish scoring, component reinvention) ahead of the
incremental coverage upgrade (multi-file). The reasoning: opening new
categories of finding moves Lumo toward the success criteria; pushing
existing `lumo-render` coverage from 28% to 60% improves what already
works but doesn't change what Lumo can answer.

### Phase 2 sequence

1. `lumo-spec` — design vs. requirements (Confluence / Jira / Notion / Markdown)
2. `lumo-tier` — Tier-1 polish composite score
3. `lumo-component` — reinvented-components detector
4. Multi-file AST resolution (lumo-render coverage 28% → 60%)
5. `rules_search` — hybrid BM25 + embeddings
6. `audit_html` — HTML report renderer (postponed)

### Tools

4. **`lumo-source` — Compose + SwiftUI AST checks**
   ✅ Compose shipped in v0.0.3 (PyPI). ✅ SwiftUI shipped in v0.0.4.
   Parses `.kt` with `tree-sitter-kotlin` and `.swift` with
   `tree-sitter-swift`. Four checks per platform:
   `undersized_tap_target` (a11y, Material 48dp / Apple HIG 44pt),
   `off_scale_spacing`, `hardcoded_color`, `off_scale_radius`. Honesty
   rule baked in: theme tokens (`MaterialTheme.*`, `LocalDimensions.*`,
   `Theme.spacing.*`, `Color("brandPrimary")`) are never flagged — only
   hardcoded literals trip a finding. Exposed as a CLI
   (`lumo-source check --file …`, language auto-detected by extension)
   and as two MCP tools (`lumo_source_check_compose`,
   `lumo_source_check_swiftui`).
5. **`lumo-audit` — whole-repo aggregator** ✅ shipped.
   Walks every `.kt` / `.swift` file under `--root`, runs `lumo-source`
   per file, and produces two views: (a) drift hotspots — counts by
   check / category / severity / language; (b) measured scale — top
   frequencies of every hardcoded padding / radius / size literal,
   partitioned on/off the configured scale. Reads its config from the
   `audit:` section of `lumo.config.json`. Always skips a hardcoded set
   of noisy dirs (`.git`, `build`, `node_modules`, `Pods`, etc.); extra
   excludes via `--exclude` glob or config. JSON output via `--json`,
   markdown summary via `--out file.md`. Exposed as the 7th MCP tool
   (`lumo_audit_scan`).
   - **Backlog** — `.lumoignore` support. A `.gitignore`-style file at
     the repo root, for projects that want fine-grained exclude rules
     versioned alongside the code. Postponed because (a) CLI `--exclude`
     globs plus the hardcoded skip list cover the common case, (b) we
     want to validate format demand against real users first, (c) the
     audit doesn't depend on git, so adopting `.gitignore` itself would
     be a hidden coupling. Land after Figma sync + snapshot capture so
     the audit's role in the lifecycle is fully understood.
6. **`lumo-figma` — Figma integration (two subcommands)**.
   - **`diff`** ✅ shipped in v0.0.8. Fetches Figma variables (COLOR +
     FLOAT) via `/v1/files/{key}/variables/local`, resolves alias
     chains and named modes, diffs by value against a `lumo-audit`
     JSON payload. Three buckets: matched / unused_in_code /
     missing_from_figma. Match key is value, never name — Figma names
     (`spacing/lg`) and code identifiers (`Dimens.lg.dp`) drift, so
     name-based join produces false negatives. Auth via `FIGMA_TOKEN`
     env. MCP tool `lumo_figma_diff`.
   - **`render`** ✅ shipped in v0.2.0. Hits `/v1/files/{key}/nodes`,
     walks the frame subtree, emits a Lumo layout JSON with
     `source: "measured"` — Figma's `absoluteBoundingBox` IS the
     post-Auto-Layout rendered coordinate. Lets `lumo-theory` /
     `lumo-parity` run on the DESIGN itself, before any code ships.
     Element ids come from layer names; role heuristics from name
     prefix (`btn_*` → primary_action, `nav_*` → nav_item, etc.).
     Hidden / null-bbox nodes are skipped, not faked. MCP tool
     `lumo_figma_render`. Design at
     [docs/design/figma-render.md](./docs/design/figma-render.md).
     - v0.2.1 — tightened role heuristic (INSTANCE + ≥32dp), nested-
       container Gestalt skip, `--platform ios|android` override.
     - v0.2.2 — extracts SOLID fills as `fg`/`bg` so the layout JSON
       carries colour. Unlocks `fitts_color_contrast` in `lumo-theory`.
   - **`annotate`** ✅ shipped in v0.2.1. Overlays severity-coloured
     boxes + numbered badges on the Figma frame PNG given a layout
     JSON and a findings JSON. Auto-fetches the PNG via
     `/v1/images?ids=` when `--png-in` is omitted. Optional Pillow
     dependency via the `[viz]` extra.
   - **Out of scope (v1):** Styles (the older Figma token system) need
     a node-tree walk and ship in a later phase. Pixel-diff of Figma
     vs rendered app lives in `snapshot_input`, not here. No mapping
     config — we match by value, so naming convention drift doesn't
     block the diff.
7. **`lumo-render` — AST layout evaluator (Compose + SwiftUI)** ✅
   shipped in v0.1.0.
   Walks the same tree-sitter AST `lumo-source` already produces, but
   instead of running drift checks it *evaluates* the layout: an
   offset-stack interpreter for `Column` / `Row` / `Box` (Compose) and
   `VStack` / `HStack` / `ZStack` (SwiftUI) plus the common modifier
   transforms produces measured-like `(x, y, w, h)` for every element
   that can be statically resolved. Both platforms share the same
   evaluator core; only the parsing front-end and the per-platform
   view / modifier tables differ. The output is a Lumo-schema layout
   JSON ready to feed `lumo-theory check --from` and
   `lumo-parity diff --from`.

   Honesty hierarchy upgrade — a new label slots in between the existing
   ones:

   ```
   measured > ast-resolved > code-estimated > description-estimated
   ```

   - `ast-resolved` — value came from a static AST evaluation of known
     layout rules. Higher trust than `code-estimated` (which is "the LLM
     guessed numbers from reading code") because the evaluator is
     deterministic and refuses to invent values it cannot derive.
   - Token references (`MaterialTheme.spacing.md`), `fillMaxWidth`
     without a known screen width, `weight(1f)` siblings, runtime data,
     and unknown composables all emit `ast-unresolved` entries with a
     `reason` field — never a guessed number. Same honesty rule as
     `lumo-source`.

   Without multi-file resolution (next item below), coverage on
   typical production screens lands at **~28 %** — the rest is
   app-specific custom composables defined in other files. With
   multi-file (0.2.0) we target **≥ 60 %**; the last gap remains the
   runtime values `snapshot_input` covers.

8. **`lumo-spec` — design vs. requirements check.** ⏳ next (target 0.3.0).
   The first missing piece for a complete design audit: today
   `lumo-figma render` answers "does this layout obey the
   cognitive-science rules" and `lumo-figma diff` answers "do tokens
   match", but neither answers "does the design match the product
   requirements". This tool pulls the requirements from where they
   actually live — Confluence, Notion, Jira, Linear, or a local
   Markdown folder — and runs an LLM-backed semantic check against
   a Lumo layout JSON (from `lumo-figma render` or `lumo-render`).

   **Sources (pluggable):**
   - Confluence — page id or URL, REST API (`/wiki/rest/api/content`),
     auth via `CONFLUENCE_TOKEN` env. Plazo's primary surface
     (MobileDepartment space).
   - Notion — page / database id, official API,
     `NOTION_TOKEN` env.
   - Jira / Linear — single ticket id, REST API + LLM extracts the
     "design requirements" section.
   - Local Markdown — `--spec ./prd.md` for offline / monorepo cases.

   **What it does:**
   - Fetches the spec doc, flattens to text (ADF → markdown for
     Atlassian, blocks → markdown for Notion).
   - Takes the layout JSON (Lumo schema, any source label) as
     "what's currently designed".
   - LLM-backed semantic comparison: emits findings like
     *"spec requires a back button — not present in layout"*,
     *"spec calls for 3 input fields, layout has 5"*,
     *"spec says hide CTA until form valid — layout shows it
     always"*.
   - Honesty rule: findings carry `confidence` field (`high`
     when textual evidence is direct, `medium` for inferred, `low`
     for soft heuristics). Never fabricate requirements the spec
     doesn't state.
   - Output: same Lumo finding shape as `lumo-theory`; severity
     derived from spec wording (`must` → high, `should` → medium,
     `may` → low).

   **CLI shape (proposed):**
   ```bash
   lumo-spec check --layout screen.json \
                   --source confluence --page-id 123456
   lumo-spec check --layout screen.json \
                   --source notion --page-id <uuid>
   lumo-spec check --layout screen.json --spec ./prd.md
   lumo-spec check --layout screen.json --jira CRDES-1234
   ```

   **Out of scope (v1):**
   - No write-back to the spec source — read-only.
   - No spec authoring / templating. The team writes the spec how
     they want; Lumo reads it.
   - No multi-page consolidation in v1 — one spec input per check.

   **Honesty risk to call out early:** LLM-backed checks have higher
   drift than the deterministic Python tools. This tool's findings
   must carry a clear "LLM-derived" marker and never claim
   `source: "measured"`. The `confidence` field is non-negotiable.
   Design doc: [docs/design/spec-check/](./docs/design/spec-check/) —
   split into README + 8 sub-docs (inputs, algorithm, outputs,
   sources, honesty, testing, risks, phasing).

9. **`lumo-tier` — Tier-1 polish composite score.** ⏳ planned (target 0.4.0).
   Answers the central question of Lumo's success criteria:
   *"Is this design Tier 1, and if not, exactly why?"* Composes nine
   deterministic sub-metrics into a weighted score (0–100) and a tier
   bucket (Tier 1 / Tier 2 / Tier 3). Every sub-metric ships as its
   own check so findings stay actionable.

   **Metrics (computed from a Lumo layout JSON, no LLM):**

   | Metric | How measured |
   |---|---|
   | `typography_discipline` | Count of unique font sizes per screen (target ≤ 3); ratio between adjacent sizes (target 1.25 / 1.333 / 1.5). |
   | `spacing_rhythm` | All paddings / margins ∈ configured scale (`audit.spacing_scale`); count of orphan values. |
   | `palette_economy` | Count of unique colours per screen (target ≤ 7); all colours resolve to tokens (no orphan hex). |
   | `consistency` | Same role → same size + spacing (e.g. all `primary_action` heights match, all `nav_item` paddings match). |
   | `symmetry` | Left/right margin parity; weight distribution against vertical centre. |
   | `hierarchy_clarity` | Primary action ≥ 1.5× visual weight vs secondary (extends current Fitts relative check). |
   | `gestalt_grouping` | Within-group spacing ≤ ½ × between-group spacing (proximity ratio). |
   | `guideline_conformance` | Compliance with configured platform catalogue (HIG / Material 3); see `platform_guidelines` config below. |
   | `radius_consistency` | Count of unique radius values per screen (target ≤ 2); all radii ∈ configured `radius_scale`. |

   **Score → Tier:**
   - Tier 1: ≥ 85, zero `high`-severity sub-metric failures.
   - Tier 2: 65–84, or any single `high` failure.
   - Tier 3: < 65, or ≥ 2 `high` failures.

   Weights live in `lumo.config.json` so teams can tune to their
   priorities (e.g. brand-led teams might weight `palette_economy`
   higher; accessibility-led teams weight `hierarchy_clarity`).

   **CLI shape (proposed):**
   ```bash
   lumo-tier score --layout screen.json
   lumo-tier score --layout screen.json --config lumo.config.json
   lumo-tier score --layout screen.json --json
   ```

   **Output contract:** verdict line (`TIER 1 — score 92`), per-metric
   table (metric / score / weight / contribution / status), then the
   normal Lumo findings list for everything that lost points. No
   reference apps, no LLM scoring — every point lost has a measurable
   cause.

   **What this is NOT:** subjective polish, brand judgement, copy
   review, animation quality, or anything that can't be derived from
   geometry + tokens. Tier-1 here means "passes the measurable polish
   bar", not "wins design awards".

10. **`lumo-component` — reinvented-components detector.** ⏳ planned
    (target 0.4.0 — pairs with `lumo-tier`).
    Catches the pattern: developer rebuilds a platform-provided
    component from primitives instead of using the off-the-shelf
    version, dragging in boilerplate + accessibility gaps + drift
    from platform behaviour.

    **Detection (AST pattern matching on `lumo-source` output):**
    - Compose: `Surface { Row { Icon; Text; Spacer; Icon } }` with
      `clickable` → "use `ListItem`". `Box { Text; CircularProgressIndicator }`
      with explicit padding → "use `Button(content = …)` with loading slot".
      `Row { Checkbox; Text }` → "use `CheckboxRow` / `LabelledCheckbox`".
    - SwiftUI: `HStack { Image; Text; Spacer; Image }` with `.onTapGesture`
      → "use `Label` + `Button`". Custom toggle built from
      `Rectangle().fill(…)` → "use `Toggle`".

    **Config-driven (mandatory):**
    ```json
    {
      "platform_guidelines": {
        "android": "material3",
        "ios":     "hig"
      },
      "component_library": {
        "source": "platform",
        "allowed_reinvention": [
          "LimitExceededDialog",
          "RegistrationStepHeader"
        ]
      }
    }
    ```
    - `platform_guidelines.android` ∈ `material3 | material2 | custom`.
    - `platform_guidelines.ios` ∈ `hig | custom`.
    - `component_library.source` ∈ `platform | custom | mixed`.
      `platform` means primitives should resolve to first-party
      components (Material 3 / SwiftUI). `mixed` allows internal
      design-system components in addition. `custom` disables the
      check entirely.
    - `allowed_reinvention` whitelists business-level composites
      (Plazo's `LimitExceededDialog`, registration screens, etc.) —
      these are *intended* reinvention and never flagged.

    **Output:** finding shape consistent with `lumo-source`, severity
    `medium` by default (`high` when the reinvention drops a11y
    behaviour the platform component provides for free — e.g. custom
    toggle missing `.accessibilityValue`).

    **What this is NOT:** a code generator (no auto-replace, only
    suggestion). Does not require a design-system library to exist —
    works directly against platform components in v1.

11. **Multi-file AST resolution.** ⏳ planned (target 0.5.0,
    deprioritised from 0.3.0).
    Incremental coverage upgrade for `lumo-render`: walk the project
    when an unknown composable is encountered, find its definition,
    parse that file, and inline the body — the honesty rule still
    applies (anything we can't resolve still emits `ast-unresolved`
    with a reason). Lifts `lumo-render` coverage from ~28% to ≥ 60%
    on typical screens. Full design split across five sub-docs under
    [docs/design/multi-file-resolution/](./docs/design/multi-file-resolution/):
    project index → name resolution → inline expansion → modifier
    forwarding → end-to-end trace. Four-phase rollout, one PR per phase.

    **Why deprioritised:** opens no new finding categories; only
    improves the precision of the AST evaluator that already works.
    Categories (`lumo-spec`, `lumo-tier`, `lumo-component`) move
    Lumo toward its success criteria first; multi-file lands once
    those three are stable and dogfooded.

12. **`rules_search`** — hybrid BM25 + local embedding search over rules DB.
13. **`audit_html`** — optional HTML report renderer for `lumo-audit`.
    Postponed: would add a templating dep (jinja2 etc.) and Socket will
    flag the new attack surface. The current markdown / JSON output is
    enough for CI consumption; revisit after dogfood.

### Data

- Expand `platform_rules` to full HIG + Material catalogue.
- Expand `parity_table` to 150+ pairs.
- Per-project memory store (populated by `lumo-audit` after user confirmation).

### Content

- Medium article: "Why I built a Claude skill that uses Fitts's Law instead of just HIG"
- YouTube demo (60–90 sec)
- Instagram reel (15–30 sec split-screen parity diff)

---

## Phase 3 — Polish & Reach (v0.6–1.0)

### Tools

14. **`snapshot_input` — measured coordinates via capture libraries.**
    Moved here from Phase 2 once `lumo-render` lands. Ships two thin
    libraries (`lumo-android-capture` for Roborazzi, `lumo-ios-capture`
    for `swift-snapshot-testing`) that emit Lumo-schema JSON next to the
    bitmap, stamped `source: "measured"`. Earns its keep on screens where
    `lumo-render` falls back to `ast-unresolved` — runtime token
    resolution, dynamic type, weight siblings, lazy lists. Acceptance
    criteria + design in
    [docs/design/snapshot-input.md](./docs/design/snapshot-input.md).
15. Visual diff: render Compose preview + SwiftUI snapshot → pixel/structural diff.
16. Per-project memory recall — skill automatically pulls learned patterns into reviews.

### Distribution

- Submit to awesome-skills.com and ComposioHQ/awesome-claude-skills.
- Cross-post on DEV.to, Reddit (r/FlutterDev, r/iOSProgramming, r/androiddev), Hacker News.
- Twitter/X thread with GIFs.

### Stability

- Test suite for every tool.
- CI: verify against latest HIG / Material releases.

---

## Phase 4 — Beyond Skill (v1.0+, deferred)

Architecturally enabled, not built in v1.

### Tiered accuracy hierarchy (long-term shape)

The three render paths sit on a clear cost / accuracy / portability curve:

| Tier | Tool | Cost | Accuracy | Portability |
|---|---|---|---|---|
| 1 | `lumo-render compose/swiftui` (shipped 0.1.0) | ~0s, zero deps | ast-resolved (~60–80% on typical screens, 20–30% on heavily themed) | Any machine, any project state |
| 2 | `snapshot_input` (Phase 3, planned) | seconds — runs an existing snapshot test | measured | Requires the project to have Roborazzi / swift-snapshot-testing tests |
| 3 | **`lumo-build` — LLM-driven runtime evaluator** | minutes — compiles + runs | measured | Requires full toolchain (Android SDK + Gradle, or Xcode + simctl), buildable module, macOS for iOS |

`lumo-build` is the *optional fallback* the AI client invokes when it
has access to the toolchain AND the user explicitly asks for the
highest accuracy. The model would:

- **Compose:** generate a temp Paparazzi / Roborazzi test wrapping the
  target `@Composable`, run `./gradlew :module:testDebugUnitTest`
  headless, parse the `ViewInfo` tree (or a small custom dumper),
  serialise to Lumo JSON with `source: "measured"`.
- **SwiftUI:** generate a temp XCUITest that hosts the `View`, run
  `xcodebuild test` against a booted simulator, dump
  `XCUIApplication`'s accessibility tree, serialise to the same JSON.

**Why this is "consider only after snapshot_input ships":** the
engineering cost is high (per-project build config awareness, Paparazzi
version sniffing, mac-only for iOS, KMP multi-target gotchas, broken
modules), and the value is duplicative of `snapshot_input` — both end
at `source: "measured"`. `snapshot_input` requires user test
infrastructure but is point-of-use simple; `lumo-build` requires no
test infrastructure but is orchestrator-heavy. Ship `snapshot_input`
first, see demand, then decide.

**This is NOT a 0.x.y target.** Tracking here so the option doesn't
get lost; not on any active sprint.

### Other Phase 4 ideas

- GUI installer (Electron / Tauri).
- Flutter + React Native support.
- Optional cloud companion: team sync, cross-project memory, opt-in telemetry.
- Monetization (Pro tier, team accounts) — only if v1 gets traction.

---

## Non-goals

To prevent scope creep, Lumo is **not**:

- A code generator (it reviews and audits, doesn't write screens).
- A design tool (no canvas, no drawing).
- A replacement for Figma, Mobbin, or Specify.
- Backend-coupled in v1 (everything runs locally on the user's machine).
- Multi-platform-everything in v1 (Flutter / RN come later).
