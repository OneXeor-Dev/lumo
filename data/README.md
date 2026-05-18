# data/

Placeholder directory.

As of v0.0.7 the rules used by Lumo tools (touch-target thresholds,
animation ranges, platform-specific defaults, parity whitelists, default
spacing / radius scales) still live **inline** in each tool's source
code:

- `tools/lumo/theory/core.py` — Fitts, Hick, Gestalt, reach thresholds
- `tools/lumo/parity/core.py` — Material vs Apple HIG whitelist
- `tools/lumo/wcag/core.py` — WCAG AA / AAA thresholds
- `tools/lumo/source/core.py` — Material 48dp / HIG 44pt minimums,
  default spacing and radius scales
- `tools/lumo/audit/core.py` — hardcoded skip directories
  (`.git`, `build`, `Pods`, `node_modules`, etc.)
- `tools/lumo/figma/core.py` — Figma API base URL, default missing-token
  threshold, supported Figma variable types

`lumo-audit` and `lumo-source` share the same scale defaults today via
direct imports — not via this directory. So far that has been adequate;
the rule count is still small and each constant has one source of truth.

This directory will start hosting JSON when a third consumer needs the
same rule and a rebuild becomes painful. Likely candidates: the upcoming
Figma-sync and snapshot-input tools (Phase 2.4 / 2.5) — both need access
to the platform-rules baseline to validate measured layouts against the
design system.

Until then, don't add files here. Inline > premature data extraction.

See `ROADMAP.md` for the Phase 2 plan.
