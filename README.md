# Lumo

> Mobile UI/UX design intelligence for AI coding assistants, grounded in
> cognitive science — not just style guides.

**Status:** WIP, pre-v0.1. Three tools work, an MCP server exposes them
to every major AI client, and five different install paths are wired up.
Demo content (GIFs, video) comes next.

Lumo helps mobile developers build polished, accessible UI by applying
**Fitts**, **Hick**, **Gestalt**, and **Nielsen** alongside Apple HIG and
Material Design. The hard checks (WCAG luminance, OKLCH correction,
cross-platform diff) run as **deterministic Python tools**, not LLM
guesses.

## What works today

| Tool | What it does |
|---|---|
| `lumo-wcag` | WCAG AA / AAA contrast checker + OKLCH auto-correct that preserves chroma and hue. Catches the contrast pairs Claude misjudges by eye. |
| `lumo-theory` | Cognitive-science layout checks: undersized tap targets, relative Fitts difficulty for primary actions, Hick overload in equal-weight choice groups, Gestalt proximity violations, one-handed reachability. |
| `lumo-parity` | Cross-platform diff between Android (Compose / XML, in dp) and iOS (SwiftUI / UIKit, in pt). Flags size and component mismatches. Whitelists known platform divergences (Material 48 dp vs Apple HIG 44 pt, etc.) so the noise stays out. Optional `lumo.config.json` validates both platforms against shared design tokens. |
| `lumo-mcp` | Model Context Protocol server. Exposes all of the above to Claude Code, Cursor, Continue, Aider, Goose, Zed, OpenAI Codex CLI, and any other MCP-aware client. |

Each tool returns structured findings (severity, recommendation, metric)
and propagates an honest confidence label — `measured`, `code-estimated`,
or `description-estimated` — so the consumer can weigh the result.

## Install

Pick the path that fits your workflow:

### 1. One-command installer (`@onexeor/lumo`)

```bash
npx @onexeor/lumo init                    # interactive — picks your AI client
npx @onexeor/lumo init --ai claude        # explicit target
npx @onexeor/lumo init --all              # install everywhere supported

# After install the binary is just `lumo`:
lumo doctor
lumo uninstall --ai claude
```

Installs Python tools into `~/.lumo/venv`, copies the skill bundle into
your chosen AI client, and registers the MCP server in that client's
config. See [installer/README.md](./installer/README.md) for the full
flag list. Also ships `lumo doctor` and `lumo uninstall`.

### 2. `npx skills add` (vercel-labs/skills)

```bash
npx skills add OneXeor/lumo
```

The `skills.json` manifest at the repo root makes Lumo a first-class
citizen of the `npx skills` ecosystem. Works for any client supported
by the `skills` CLI.

### 3. Claude Code plugin marketplace

```bash
claude plugin marketplace add OneXeor/lumo
claude plugin install lumo@lumo
```

Uses the `.claude-plugin/marketplace.json` manifest — same pattern as
`apple-skills` and other native Claude Code plugins.

### 4. Direct Python install (no AI client)

```bash
pipx install lumo-mobile          # global CLI install
# or
pip install lumo-mobile           # any existing venv
```

Gives you the four CLIs (`lumo-wcag`, `lumo-theory`, `lumo-parity`,
`lumo-mcp`) without touching any AI client config. Use this if you want
to wire Lumo into CI, scripts, or a custom workflow.

### 5. Git clone + manual

```bash
git clone https://github.com/OneXeor/lumo.git
cp -r lumo/skill ~/.claude/skills/lumo
cd lumo/tools && pip install -e .
```

Zero-installer fallback for users who prefer to see every file move
themselves (the [`material-3-skill`](https://github.com/hamen/material-3-skill)
model).

## Why Lumo

Most AI design skills regurgitate platform style guides. Lumo is different
in three ways:

1. **Cognitive science first.** Numeric thresholds derived from Fitts /
   Hick / Gestalt research, applied as concrete checks. Where the
   underlying constants are device-dependent and shaky (absolute Fitts
   movement time in ms), Lumo reports relative comparisons instead of
   inventing numbers.
2. **Cross-platform parity.** Catches the classic junior bug — writing
   `padding(16.dp)` on Android and `.padding(48)` on SwiftUI under the
   "iOS uses 3× because Retina" misconception — and any other size or
   presence drift between the two platforms.
3. **Deterministic tools, not just prompts.** Real W3C luminance math,
   real OKLCH conversion, real geometric checks. None of the four shipped
   tools depends on an LLM at runtime.

## Target platforms (v1)

- **Android:** Jetpack Compose + XML layouts
- **iOS:** SwiftUI + UIKit

Flutter and React Native are on the v2 roadmap.

## Running locally for development

```bash
git clone git@github.com:OneXeor/lumo.git
cd lumo/tools
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Smoke
lumo-wcag check --fg "#3B82F6" --bg "#FFFFFF"
lumo-theory check --layout ../examples/theory_bad_layout.json
lumo-parity diff \
  --android ../examples/parity_android.json \
  --ios     ../examples/parity_ios.json \
  --config  ../examples/lumo.config.json

# Tests
pytest        # 67 passing
```

## License

MIT — see [LICENSE](./LICENSE).
