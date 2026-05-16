# Lumo

> AI design intelligence for mobile apps, grounded in cognitive science — not just style guides.

**Status:** WIP, pre-v0.1. Three tools work; the npm installer and demo content are next.

Lumo is a Claude Code skill plus a local Python toolkit. It helps mobile
developers build polished, accessible UI by applying cognitive science
(Fitts, Hick, Gestalt) alongside Apple HIG and Material Design.

## What works today

| Tool | What it does |
|---|---|
| `lumo-wcag` | WCAG AA / AAA contrast checker + OKLCH auto-correct that preserves chroma and hue. Catches the 30 – 40 % of pairs Claude misjudges by eye. |
| `lumo-theory` | Cognitive-science layout checks: undersized tap targets, relative Fitts difficulty for primary actions, Hick overload in equal-weight choice groups, Gestalt proximity violations, one-handed reachability of primary actions. |
| `lumo-parity` | Cross-platform diff between Android (Compose / XML) and iOS (SwiftUI / UIKit). Flags spacing / sizing / component mismatches. Whitelists known legitimate platform divergences (Material 48 dp vs Apple HIG 44 pt, etc.) so the noise stays out. Optional `lumo.config.json` validates both platforms against shared design tokens. |

Each tool is invoked from the Lumo Claude Code skill via Bash, returns
structured findings (severity, recommendation, metric), and propagates an
honest confidence label — `measured`, `code-estimated`, or
`description-estimated` — so the user can weigh the result.

## What's coming

See [ROADMAP.md](./ROADMAP.md). Short version: npm installer for zero-setup,
then Figma sync, AST-based codebase audit, and a hybrid BM25 + local
embedding rules search.

## Why Lumo (vs. the alternatives)

Most AI design skills regurgitate platform style guides. Lumo is different
in three ways:

1. **Cognitive science first.** Numeric thresholds derived from Fitts /
   Hick / Gestalt research, applied as concrete checks. Where the
   underlying constants are device-dependent and shaky (absolute Fitts MT
   in ms), Lumo reports relative comparisons instead of inventing numbers.
2. **Cross-platform parity.** Catches the classic junior bug — writing
   `padding(16.dp)` on Android and `.padding(48)` on SwiftUI under the
   "iOS uses 3 × because Retina" misconception — and any other size /
   presence drift between the two.
3. **Deterministic tools, not just prompts.** Real W3C luminance math,
   real OKLCH conversion, real geometric checks. None of the three core
   tools depends on an LLM at runtime.

## Target platforms (v1)

- **Android:** Jetpack Compose + XML layouts
- **iOS:** SwiftUI + UIKit

Flutter and React Native are on the v2 roadmap.

## Running it locally (before the installer ships)

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
pytest
```

The Claude Code skill itself lives under `skill/SKILL.md`. Point your
Claude Code at the repo as a plugin or copy the skill into your local
skills directory — once the npm installer lands that step becomes
`npx lumo init`.

## License

MIT — see [LICENSE](./LICENSE).
