# data/

Placeholder directory.

In v0.1 the rules used by Lumo tools (touch-target thresholds, animation
ranges, platform-specific defaults, parity whitelists) live **inline** in
each tool's source code:

- `tools/lumo/theory/core.py` — Fitts, Hick, Gestalt, reach thresholds
- `tools/lumo/parity/core.py` — Material vs Apple HIG whitelist
- `tools/lumo/wcag/core.py` — WCAG AA / AAA thresholds

This is adequate while the rule count is small and there is only one
consumer per rule. The rules move into this directory once a second
consumer needs to read them — specifically, the Phase 2 `codebase_audit`
tool will need to share the platform-rules baseline with the existing
parity checker.

Until then this directory intentionally has no other files. Don't
add data here yet — wait until the audit lands so we can design the
file layout against an actual use case rather than guessed structure.

See `ROADMAP.md` for the Phase 2 plan.
