# Changelog

All notable changes to Lumo are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and Lumo adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
