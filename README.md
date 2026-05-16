# Lumo

> AI design intelligence for mobile apps, grounded in cognitive science — not just style guides.

**Status:** WIP (pre-v0.1)

Lumo is a Claude Code skill + local toolkit that helps mobile developers build polished, accessible UI by applying cognitive science (Fitts's Law, Hick's Law, Gestalt principles, Nielsen heuristics) alongside Apple HIG and Material Design.

## Why Lumo

Most AI design skills regurgitate platform style guides. Lumo is different in three ways:

1. **Cognitive science first.** Numeric thresholds derived from Fitts/Hick/Gestalt research, not opinion.
2. **Cross-platform parity.** Catches numeric drift between Compose and SwiftUI (and XML / UIKit) for the same feature.
3. **Real tools, not just prompts.** WCAG luminance validator, OKLCH auto-correct, Figma sync, AST-based codebase audit — things Claude alone cannot do reliably.

## Target Platforms (v1)

- **Android:** Jetpack Compose + XML layouts
- **iOS:** SwiftUI + UIKit

Flutter and React Native are on the roadmap.

## Status

This is a public-facing build log of a side project. See [ROADMAP.md](./ROADMAP.md) for what's planned.

## License

MIT — see [LICENSE](./LICENSE).
