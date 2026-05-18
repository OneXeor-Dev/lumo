# Changelog

All notable changes to Lumo are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and Lumo adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.8] — 2026-05-18

### Added

- **`lumo-figma`** — diff Figma design tokens against the audited code.
  Fetches COLOR + FLOAT variables from the Figma REST API
  (`/v1/files/{key}/variables/local`), resolves alias chains, picks a
  named mode (or each collection's default), and compares against a
  `lumo-audit --json` payload. Three buckets in the diff:
  - **matched** — token value present in Figma AND in code, with code
    occurrence count from the audit.
  - **unused_in_code** — token declared in Figma but no literal in code
    matches its value. Treated as **candidates for review**, not a
    hit-list for deletion — theme indirection
    (`MaterialTheme.colorScheme.*`, `LocalDimensions.*`,
    `Color("brandPrimary")`) is invisible to the AST audit, so a token
    may still be used via the design-system layer.
  - **missing_from_figma** — value used in code ≥ `--missing-threshold`
    times (default 3) with no Figma token. Strong candidate for
    promotion to the design system.
- **Match by value, not by name.** Figma names (`spacing/lg`) and code
  identifiers (`Dimens.lg.dp`, `Theme.spacing.large`) drift across
  projects. The only stable join key is the resolved hex / number.
  Names appear in the report for human reference, never as a match key.
- New MCP tool `lumo_figma_diff` — server now exposes **8 tools**.
- `lumo-figma diff` CLI accepts `--file-key` or `--url`, `--audit` JSON
  file or `--root` for inline scan, `--mode <name>`, `--missing-threshold`,
  `--json`, and `--out <file.md>`. Auth via `FIGMA_TOKEN` env var only —
  never via CLI flags (would leak into shell history).
- 22 new tests in `tests/test_figma.py` covering URL parsing (file/design/
  proto/board paths, node-id normalisation), payload parsing (COLOR +
  FLOAT, alias chains, alias cycles, mode selection, unknown types
  dropped), HTTP layer via `httpx.MockTransport` (header, 4xx error
  surfacing, env-var fallback, missing-env error), and diff math
  (value-only matching, threshold cutoff, hex normalisation, empty
  inputs). One new MCP wrapper-parity test. Suite: **154/154 pass,
  mypy strict clean**.
- CI gains a smoke check that asserts `lumo-figma` produces a clean
  `FIGMA_TOKEN`-missing error when invoked without auth.
- `httpx` added as an explicit dependency in `pyproject.toml`. It was
  already pulled in transitively via `mcp`; making it explicit avoids
  a surprise break if `mcp` ever drops it.
- `lumo-figma` script added to the installer's
  `listInstalledBinaries` (7 expected console scripts now).

### Out of scope (v1)

- **Figma styles** — the older token system (paint/text/effect
  styles). Requires a node-tree walk to extract values. Lands in a
  follow-up once variables coverage proves the diff model.
- **Frame-by-frame layout diff** — comparing screen geometry against
  Compose / SwiftUI screens is a different problem; lives behind the
  `snapshot_input` capture libraries in Phase 2.5.
- **Name-aware matching** — no `figma.mapping` config in
  `lumo.config.json` yet. Add only if real user cases show name-aware
  matching is materially better than value-only.

## [0.0.7] — 2026-05-18

### Added

- **`lumo-audit`** — whole-repository design-system audit. Walks every
  `.kt` / `.kts` / `.swift` file under `--root`, runs `lumo-source` on
  each, and aggregates two views:
  - **Drift hotspots.** Counts of findings by check, category,
    severity, and language. Tells you *what* to prioritise refactoring.
  - **Measured scale.** Frequency tables for every hardcoded padding /
    radius / size literal. Compares the top values against the
    configured scale to surface actual drift — strictly more useful
    than "this one file violates a rule." Token references
    (`MaterialTheme.spacing.md`, `Theme.spacing.md`,
    `Color("brandPrimary")`) are intentionally invisible so the table
    measures real literals, not theme usage.
- New MCP tool `lumo_audit_scan` exposes the same API. The MCP server
  now ships **7 tools total**.
- `lumo.config.json` gains an `audit:` section (`spacing_scale`,
  `radius_scale`, `exclude`, `top_n_values`). CLI flags override the
  config-file values.
- Hardcoded skip directories baked in: `.git`, `.gradle`, `build`,
  `Pods`, `DerivedData`, `node_modules`, `dist`, `out`, `__pycache__`,
  `.venv`, `venv`, `.idea`, `.pytest_cache`. Pass `--exclude <glob>`
  for additional project-specific filters.
- 17 new tests in `tests/test_audit.py` (positive + negative per check,
  scale-bucketing, top-N cap, language-only-when-present aggregation).
  Two new MCP wrapper tests. Suite: **131/131 pass, mypy strict clean**.
- CI e2e gains `lumo-audit scan --root examples` smoke check verifying
  the aggregate output mentions `undersized_tap_target: 2`, scale
  observations, and the `Off-scale values:` line.

### Notes

- `.lumoignore` support is **deliberately deferred** — see the Backlog
  section of `ROADMAP.md`. The hardcoded skip list plus CLI `--exclude`
  globs cover the common case; we want real-user feedback before
  introducing a new file format.
- HTML report rendering is also deferred (markdown + JSON outputs are
  enough for CI, and adding a templating dep would re-introduce supply-
  chain surface that Socket would flag). Logged in ROADMAP as `audit_html`.

## [0.0.6] — 2026-05-17 (both PyPI + npm — version-sync release)

### Changed

- **Versions now sync across PyPI and npm.** `lumo-mobile` (PyPI) and
  `@onexeor/lumo` (npm) drifted apart during the early supply-chain
  fixes: PyPI sat at 0.0.4 while npm reached 0.0.5. From now on **both
  packages bump together to the same number** — even when only one side
  changed code. Easier to reason about, easier to support. This release
  pulls PyPI all the way to 0.0.6 to catch up with npm in one move,
  rather than leaving them one apart again.
- **Fresh skill bundle in the npm tarball.** `installer/skill/` is
  regenerated by `installer/scripts/bundle-skill.js` and now ships
  `lumo-source` for both Compose and SwiftUI. The 0.0.5 npm tarball
  still carried a SKILL.md from v0.0.1 — every `npx @onexeor/lumo init`
  was installing an outdated skill without the source-AST tool. Missing
  the bundle-skill step at release time was the root cause.
- **CI e2e now exercises `lumo-source`** end-to-end against two anchor
  files: `examples/source_bad_compose.kt` and
  `examples/source_bad_swiftui.swift`. Each has one finding per check
  category plus counter-cases (`MaterialTheme.*`, `Color.red`,
  `Color("brandPrimary")`) that must NOT trigger. Five console scripts
  must exist after install, not four.
- README — `the three CLIs` → `the Lumo CLIs`; `four shipped tools` →
  rephrased to drop the count and mention `tree-sitter` AST walking.

### Notes

- PyPI 0.0.6 is a **version-sync release** — the Python code is
  identical to 0.0.4. No new behaviour, no new tools, no new
  dependencies. Only `version` strings change. (PyPI 0.0.5 was never
  published; we jumped 0.0.4 → 0.0.6 deliberately to land both
  registries on the same number in one move.)
- npm 0.0.6 ships the SKILL bundle update; without it `npx init` would
  continue installing a SKILL.md that doesn't mention `lumo-source`.

## [0.0.4] — 2026-05-17

### Added

- **SwiftUI support in `lumo-source`.** The same four checks
  (`undersized_tap_target`, `off_scale_spacing`, `hardcoded_color`,
  `off_scale_radius`) now apply to `.swift` files via `tree-sitter-swift`.
  - Apple HIG minimum tap target = **44pt** (not the Compose 48dp).
  - SwiftUI uses bare `pt` numbers — `.padding(16)` not `.padding(16.dp)`.
  - Colour check recognises `Color(red:green:blue:)`,
    `Color(.sRGB, red:..., green:..., blue:...)`, and skips named
    constants (`Color.red`), asset-catalog lookups (`Color("brand")`),
    and `Color(hex: "…")` custom extensions per the honesty rule.
  - Same spacing/radius scales as Compose — dp and pt are physically
    equal on screen, so the budget transfers unchanged.
- **`lumo-source` language auto-detect**: language inferred from the
  file extension (`.kt`, `.kts`, `.swift`). Required `--lang kotlin|swift`
  when reading from stdin.
- New MCP tool `lumo_source_check_swiftui` wrapping the same API. The
  MCP server now exposes 6 tools total.
- 23 new tests in `tests/test_source_swiftui.py` covering positive +
  negative cases per check, plus 2 new wrapper-parity tests in
  `tests/test_mcp.py`. Suite: 114/114 pass, mypy strict clean.

## [0.0.3] — 2026-05-17

### Added

- **`lumo-source`** — AST-based design-system drift checks for Jetpack
  Compose. Parses `.kt` files with `tree-sitter-kotlin` and flags four
  patterns the layout-based checks can't see without runtime data:
  - `undersized_tap_target` (a11y, high) — `Modifier.size(N.dp)` with `N<48`
  - `off_scale_spacing` (consistency, medium) — padding off the scale
  - `hardcoded_color` (token, medium) — raw `Color(0xFF…)` constants
  - `off_scale_radius` (consistency, low) — `RoundedCornerShape` off scale
  - Token references (`MaterialTheme.*`, `LocalDimensions.*`) are
    intentionally **not** flagged — we cannot resolve runtime values
    statically, so the honest answer is to skip rather than guess.
- New MCP tool `lumo_source_check_compose` wrapping the same API.
- `lumo-source` exposed as a console script (`pip install lumo-mobile`
  now installs the binary alongside `lumo-wcag` / `lumo-theory` /
  `lumo-parity` / `lumo-mcp`).
- 20 unit tests in `tests/test_source.py` covering positive + negative
  cases for every check, plus aggregation and custom-scale paths.

## [0.0.5] — 2026-05-17 (installer only)

### Changed

- Removed inline markdown URL links from `installer/README.md`. Socket
  flags string-encoded URLs in package content as a supply-chain risk
  signal even when the URL is in documentation. The remaining URL is
  in `package.json#repository.url`, which is a required npm field used
  by the npm.js page to show the Repository link — we keep it
  deliberately.
- No behaviour change: the installer CLI works exactly as in 0.0.4.

## [0.0.4] — 2026-05-17 (installer only)

### Changed

- **Zero npm dependencies.** Removed `commander`, `kleur`, and `prompts`
  from the installer in favour of Node built-ins and tiny in-tree helpers
  (`src/lib/style.js`, `src/lib/prompt.js`). Two reasons:
  1. Socket.dev dependency alerts on @onexeor/lumo 0.0.3 came from these
     three packages — `URL strings` and `Environment variable access`
     supply-chain signals plus an `Unmaintained` flag on `sisteransi`
     (a transitive dep of `prompts`, last released 2020). With zero
     deps the dependency-tree surface area Socket scans is now empty.
  2. The total replacement cost is small — argument parsing moved to
     `node:util` `parseArgs` (Node ≥18.3), styling is six ANSI helpers,
     and the prompt is a 60-line numbered-list select that falls back
     to the first option on non-TTY stdin.
- `engines.node` bumped from `>=18` to `>=18.3` for `parseArgs`.

### Notes

- No user-facing CLI surface change. `lumo init`, `lumo doctor`,
  `lumo uninstall` all accept the same flags and behave the same way.
- Smoke-tested end-to-end on a fresh machine: `npm install` shows
  `└── (empty)`, `lumo init --ai claude --dev --no-mcp` runs through,
  `lumo doctor` reports green.

## [0.0.3] — 2026-05-17 (installer only)

### Changed

- **Supply-chain hygiene.** Removed the `prepack` lifecycle script from
  `installer/package.json`. Socket.dev (and other npm supply-chain
  scanners) flag any package that defines lifecycle hooks — even ones
  that only run on the maintainer's machine — because in principle an
  attacker could put malicious code there. Our `prepack` only copied
  `/skill` into `installer/skill` before packing, which is now done
  explicitly by `installer/scripts/release.sh` instead. No user-facing
  behaviour change: `npm install @onexeor/lumo` was never running that
  script anyway.
- Renamed the npm script from `prepack` to `bundle-skill`. Maintainers
  publishing a new version run `bash installer/scripts/release.sh`
  which bundles the skill, packs, and publishes in one shot. Also
  supports `--dry-run`.

## [0.0.2] — 2026-05-16 (installer only)

### Fixed

- `npx @onexeor/lumo init` now installs the correct PyPI package
  (`lumo-mobile`). The 0.0.1 npm tarball was published before the
  package rename and still referenced `lumo-tools`, which is not on
  PyPI — every fresh install failed with "Could not find a version
  that satisfies the requirement lumo-tools".

This is an installer-only release. The Python tools (`lumo-mobile` on
PyPI) and the Claude Code skill bundle are unchanged.

## [0.0.1] — 2026-05-16

First public release. Four working tools, five install paths, MCP support
out of the box.

### Added

- `lumo-wcag` — W3C luminance + contrast checker with OKLCH auto-correct
  that preserves chroma and hue while pushing pairs above WCAG AA / AAA.
- `lumo-theory` — cognitive-science layout checks: undersized tap
  targets, relative Fitts difficulty for primary actions, Hick overload
  in equal-weight choice groups, Gestalt proximity violations, one-handed
  reachability.
- `lumo-parity` — cross-platform diff between Android (dp) and iOS (pt)
  layouts. Component presence, sizing diff, design-system token validation,
  whitelisted platform divergences (Material 48dp vs Apple HIG 44pt, etc.).
- `lumo-mcp` — Model Context Protocol server exposing all of the above
  to Claude Code, Cursor, Continue, Aider, Goose, Zed, OpenAI Codex CLI.
- Claude Code skill (`skill/SKILL.md`) with explicit triggers, anti-triggers,
  decision tree, output contract, and worked examples per tool.
- `@onexeor/lumo` npm installer with `init / doctor / uninstall` and four
  supported AI clients (Claude, Cursor, Codex, generic).
- `lumo-mobile` published to PyPI for `pipx install lumo-mobile`.
- `skills.json` for `npx skills add OneXeor-Dev/lumo`.
- `.claude-plugin/marketplace.json` for the Claude Code plugin marketplace.
- 67 tests covering WCAG anchors (WebAIM / Material / Apple), theory
  layout cases, parity findings, and MCP wrapper parity with the
  underlying Python API.
- Example layouts (`examples/parity_*.json`, `theory_*_layout.json`,
  `lumo.config.json`) used in the SKILL.md worked examples and in CI.

### Notes

- Python tools are deterministic. None of the four shipped tools depends
  on an LLM at runtime.
- The cognitive-science checks deliberately do **not** report absolute
  Fitts MT or Hick RT in milliseconds — those depend on device-specific
  constants with ±40% variance across studies. Lumo returns relative
  ratios and discrete flags only.
- Nielsen heuristics are present in the SKILL.md as inline manual-review
  guidance but intentionally **not** in the `theory_check` tool — they
  aren't reliably numeric.

[0.0.1]: https://github.com/OneXeor-Dev/lumo/releases/tag/v0.0.1
