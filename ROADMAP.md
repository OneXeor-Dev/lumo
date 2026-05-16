# Lumo Roadmap

This document is the source of truth for what Lumo is, what it isn't, and the order of work.

---

## Foundation (locked decisions)

These are settled. Do not re-litigate without strong cause.

- **Platforms v1:** Android (Jetpack Compose + XML), iOS (SwiftUI + UIKit)
- **Distribution:** npm CLI installer (`npx lumo init`), zero backend
- **Positioning:** cognitive-science-driven, not style-guide-driven
- **Storage:** local only (LanceDB or sqlite-vec for embeddings; JSON/CSV for rules)
- **Embedding model:** local (bge-small-en-v1.5, lazy download on first use)
- **License:** MIT
- **Hero feature:** theory-of-design checks (Fitts / Hick / Gestalt / Nielsen)
- **No backend in v1:** no telemetry, no cross-user learning, no cloud sync

## Open decisions (resolve before Phase 1 code)

- Tools language: **Python** (proposed — tree-sitter for AST, numpy for math, npm wrapper installs Python deps under the hood like ruff/black do)
- npm package name: `lumo` (top-level — to be confirmed available)
- GitHub org: OneXeor

---

## Phase 1 — MVP (target: v0.1)

Goal: `npx lumo init` works end-to-end with one killer feature demonstrable on video.

### Tools (priority order)

1. **`wcag_validator`** — W3C luminance formula + OKLCH auto-correct.
   - Simplest. Pure numeric. Proves the tool plumbing works.
   - Cannot be replicated by prompting alone.

2. **`platform_parity`** — diff Compose ↔ SwiftUI for the same screen.
   - Hero demo for video / Instagram reel.
   - Checks: padding, animation duration, touch target, typography scale, color tokens.

3. **`theory_check`** — Fitts / Hick / Gestalt rules applied to screen layout.
   - Differentiator. Nobody else does this.
   - Numeric thresholds, not vibes.

### Data (curated, ships with the package)

- `platform_rules/` — baseline HIG + Material rules (touch targets, animation tokens, typography scale, safe areas) for Compose, XML, SwiftUI, UIKit.
- `theory_rules/` — Fitts (target size × distance → reaction time), Hick (choice count → decision time), Gestalt (proximity/similarity thresholds), Nielsen 10 heuristics.
- `parity_table/` — Compose ↔ SwiftUI component mapping (50–80 pairs for v0.1).

### Skill structure

```
lumo/
├── SKILL.md              # main Claude Code entrypoint
├── references/           # per-platform deep dives, theory primer
├── tools/                # Python scripts callable from the skill
├── data/                 # rules, parity tables
└── installer/            # npm CLI (init, config)
```

### Distribution

- npm package
- Public GitHub repo (currently private during build)
- README with GIF demo
- One end-to-end use case in `examples/`

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
