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

## Open decisions (resolve before publishing v0.1)

- npm package name: still need to confirm `lumo` is available on the npm registry, or fall back to `@onexeor/lumo`.

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
| 2 | `theory_check` | ✅ Shipped | Fitts (undersized + relative difficulty for primary), Hick overload, Gestalt proximity, reach rules. 17 tests. Nielsen heuristics intentionally not in the tool (not reliably numeric). |
| 3 | `platform_parity` | ✅ Shipped | Android (dp) vs iOS (pt) diff. Component presence, sizing diff, design-system token validation. Platform-specific defaults whitelisted (44 pt vs 48 dp etc.). 14 tests. |
| 4 | `mcp_server` | ✅ Shipped | Stdio MCP server (`lumo-mcp`) exposing all three tools to Claude Code, Cursor, Continue, Aider, Goose, Zed, Codex. 8 tests covering registration + wrapper parity with the underlying Python API. |

### Distribution (five install paths, all wired up)

| # | Path | Status | Notes |
|---|------|--------|-------|
| 1 | `npx @onexeor/lumo init` | ⚙️ Ready, not yet published | Custom Node installer with `init / doctor / uninstall`, 4 supported AI clients (Claude, Cursor, Codex, generic), guided interactive flow, `--dev` for contributors. Scoped name because top-level `lumo` is taken on npm. Tarball builds clean (`npm pack --dry-run` verified), installs cleanly from `.tgz` end-to-end. One `npm publish --access public` away from live. |
| 2 | `npx skills add OneXeor/lumo` | ✅ Shipped | `skills.json` manifest at repo root for vercel-labs/skills (skills.sh ecosystem). |
| 3 | `claude plugin marketplace add OneXeor/lumo` | ✅ Shipped | `.claude-plugin/marketplace.json` + `plugin.json` following the apple-skills schema. |
| 4 | `pipx install lumo-mobile` | ⚙️ Ready, not yet published | pyproject.toml has classifiers, urls, readme, license; `python -m build` produces clean wheel + sdist; `twine check dist/*` passes; name reserved (404 on PyPI). One `twine upload` away from live. |
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
├── skill/
│   └── SKILL.md          # main Claude Code entrypoint
├── tools/
│   ├── pyproject.toml
│   └── lumo/
│       ├── wcag/         # ✅ tool 1
│       ├── theory/       # ✅ tool 2
│       └── parity/       # ✅ tool 3
├── data/                 # placeholder — rules still inline
├── examples/             # ✅ layout pairs + lumo.config.json
└── installer/            # ⏳ npm CLI (next up)
```

### Distribution

- npm package (`lumo` or `@onexeor/lumo` depending on registry availability).
- Public GitHub repo (currently private during build).
- README with GIF demo of each tool.
- Example layouts already in `examples/`.

---

## Phase 2 — Differentiators (v0.2–0.5)

### Tools

4. **`figma_sync`** — Figma REST API → extract variables/styles → diff against code.
5. **`codebase_audit`** — AST scan of Compose / SwiftUI / XML / UIKit → extract spacing scale, color frequency, typography usage → propose design system rules → user confirms → save to local store.
6. **`rules_search`** — hybrid BM25 + local embedding search over rules DB.

### Data

- Expand `platform_rules` to full HIG + Material catalogue.
- Expand `parity_table` to 150+ pairs.
- Per-project memory store (populated by `codebase_audit` after user confirmation).

### Content

- Medium article: "Why I built a Claude skill that uses Fitts's Law instead of just HIG"
- YouTube demo (60–90 sec)
- Instagram reel (15–30 sec split-screen parity diff)

---

## Phase 3 — Polish & Reach (v0.6–1.0)

### Tools

7. Visual diff: render Compose preview + SwiftUI snapshot → pixel/structural diff.
8. Per-project memory recall — skill automatically pulls learned patterns into reviews.

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
