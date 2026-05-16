# lumo-mobile

Deterministic mobile UI/UX checks invoked by [Lumo](https://github.com/OneXeor-Dev/lumo) — a
Claude Code skill / MCP server / CLI toolkit for designing polished mobile
apps on Jetpack Compose, Android XML, SwiftUI, and UIKit.

Install:

```bash
pipx install lumo-mobile
```

Three CLIs (plus one MCP server) ship:

| Command | What it does |
|---|---|
| `lumo-wcag check --fg <hex> --bg <hex>` | WCAG AA / AAA contrast verdict using the W3C luminance formula. |
| `lumo-wcag fix   --fg <hex> --bg <hex>` | OKLCH auto-correct that preserves hue and chroma while pushing the contrast above the threshold. |
| `lumo-theory check --layout <path>` | Cognitive-science layout checks: Fitts (undersized targets, relative difficulty for primaries), Hick overload, Gestalt proximity, one-handed reachability. |
| `lumo-parity diff --android <path> --ios <path> [--config <path>]` | Cross-platform diff between Android (dp) and iOS (pt) layouts, with optional design-system token validation. |
| `lumo-mcp` | Model Context Protocol server (stdio) exposing all of the above to Claude Code, Cursor, Continue, Aider, Goose, Zed, Codex. |

See the [main repo](https://github.com/OneXeor-Dev/lumo) for the full SKILL.md,
examples, and rationale.

## License

MIT
