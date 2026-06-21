# lumo-mobile

Deterministic mobile UI/UX checks invoked by [Lumo](https://github.com/OneXeor-Dev/lumo) — a
Claude Code skill / MCP server / CLI toolkit for designing polished mobile
apps on Jetpack Compose, Android XML, SwiftUI, and UIKit.

Install:

```bash
pipx install lumo-mobile
```

Eight CLIs ship:

| Command | What it does |
|---|---|
| `lumo-wcag check --fg <hex> --bg <hex>` | WCAG AA / AAA contrast verdict using the W3C luminance formula. |
| `lumo-wcag fix   --fg <hex> --bg <hex>` | OKLCH auto-correct that preserves hue and chroma while pushing the contrast above the threshold. |
| `lumo-theory check --layout <path>` | Cognitive-science layout checks: Fitts (undersized targets, relative difficulty for primaries), Hick overload, Gestalt proximity, one-handed reachability. |
| `lumo-parity diff --android <path> --ios <path> [--config <path>]` | Cross-platform diff between Android (dp) and iOS (pt) layouts, with optional design-system token validation. |
| `lumo-source check --file <path>` | AST-based design-system drift checks for Jetpack Compose and SwiftUI source files. |
| `lumo-audit scan --root <path>` | Whole-repository aggregation of `lumo-source` findings and measured hardcoded spacing / radius scales. |
| `lumo-figma diff ...` | Figma variable diff against audited code values. |
| `lumo-figma render ...` | Render a Figma frame into Lumo layout JSON from measured `absoluteBoundingBox` coordinates. |
| `lumo-figma annotate ...` | Draw Lumo finding overlays on a Figma frame PNG for visual review. |
| `lumo-render compose --file <path>` / `lumo-render swiftui --file <path>` | Static AST layout evaluator that produces measured-like coordinates from Compose / SwiftUI source. |
| `lumo-mcp` | Model Context Protocol server (stdio) exposing all of the above to Claude Code, Cursor, Continue, Aider, Goose, Zed, Codex. |

See the [main repo](https://github.com/OneXeor-Dev/lumo) for the full SKILL.md,
examples, and rationale.

## License

MIT
