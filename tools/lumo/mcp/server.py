"""Lumo MCP server.

Exposes the three Lumo tools (WCAG, theory, parity) over the Model Context
Protocol so any MCP-compatible client (Claude Code, Cursor, Continue,
Aider, Goose, Zed, etc.) can call them with structured arguments.

This is a thin wrapper over the existing Python API — the heavy lifting
stays in lumo.wcag, lumo.theory, lumo.parity. Adding MCP did not change a
single line of those modules.

Transport: stdio (the MCP standard for local servers).

Run directly:
    lumo-mcp

Or for development:
    python -m lumo.mcp.server
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from lumo.audit.core import AuditConfig, scan_repo
from lumo.parity.core import DesignSystemConfig, diff
from lumo.source.core import (
    DEFAULT_RADIUS_SCALE_DP,
    DEFAULT_SPACING_SCALE_DP,
    check_compose,
    check_swiftui,
)
from lumo.theory.core import Element, Layout, Screen, check_layout
from lumo.wcag.core import auto_correct, check_pair

server = FastMCP("lumo")


# ============================================================================
# Tool 1 — WCAG check
# ============================================================================


@server.tool()
def lumo_wcag_check(
    fg: str,
    bg: str,
    level: Literal["AA", "AAA"] = "AA",
    size: Literal["normal", "large"] = "normal",
) -> dict[str, Any]:
    """Check whether a foreground/background color pair meets WCAG contrast.

    Uses the W3C relative luminance formula. Returns the exact contrast ratio,
    the required threshold for the given level + text size, and a pass / fail
    verdict. This is deterministic math, not an LLM guess.

    Args:
        fg: Foreground hex (#RGB, #RRGGBB, #RGBA, or #RRGGBBAA — alpha ignored)
        bg: Background hex (same formats)
        level: "AA" (4.5:1 normal / 3:1 large) or "AAA" (7:1 / 4.5:1)
        size: "normal" or "large" (large = ≥18pt or ≥14pt bold)

    Returns:
        Dict with fg, bg, ratio, level, size, required, passes.
    """
    result = check_pair(fg, bg, level, size)
    return asdict(result)


# ============================================================================
# Tool 2 — WCAG auto-correct
# ============================================================================


@server.tool()
def lumo_wcag_fix(
    fg: str,
    bg: str,
    level: Literal["AA", "AAA"] = "AA",
    size: Literal["normal", "large"] = "normal",
    max_iterations: int = 60,
) -> dict[str, Any]:
    """Auto-correct a failing foreground color to meet WCAG, preserving hue and chroma.

    Adjusts the foreground's L-channel in OKLCH (perceptually uniform color
    space) until the pair passes. Brand identity stays intact because chroma
    and hue are held fixed. Returns the corrected hex plus iteration count
    and direction (darken_fg / lighten_fg / unchanged).

    Args:
        fg: Foreground hex to correct
        bg: Background hex (untouched)
        level: "AA" or "AAA"
        size: "normal" or "large"
        max_iterations: safety bound on the iterative search

    Returns:
        Dict with original CheckResult, corrected_fg, corrected_bg, corrected
        CheckResult, iterations, and strategy.
    """
    result = auto_correct(fg, bg, level, size, max_iterations)
    return {
        "original": asdict(result.original),
        "corrected_fg": result.corrected_fg,
        "corrected_bg": result.corrected_bg,
        "corrected": asdict(result.corrected),
        "iterations": result.iterations,
        "strategy": result.strategy,
    }


# ============================================================================
# Tool 3 — theory_check
# ============================================================================


@server.tool()
def lumo_theory_check(layout: dict[str, Any]) -> dict[str, Any]:
    """Run cognitive-science layout checks (Fitts, Hick, Gestalt, reach).

    Accepts a layout JSON (same schema as the lumo-theory CLI). Returns
    findings with severity, recommendation, and the metric that produced
    them. Each finding inherits a confidence label from the layout's
    `source` field — `measured` / `code-estimated` / `description-estimated`
    — so the consumer can weigh trust honestly.

    Tool does NOT produce absolute Fitts MT or Hick RT in ms. Those depend
    on device-specific constants with ±40% variance; we return relative
    ratios and discrete flags instead.

    Args:
        layout: Layout JSON with keys `screen` ({width, height, unit}),
                `source` (one of measured | code-estimated |
                description-estimated), and `elements` (list of element
                dicts with id, role, x, y, w, h, optional group + weight).

    Returns:
        Dict with `source`, `counts_by_severity`, and `findings` list.
    """
    screen = Screen(
        width=float(layout["screen"]["width"]),
        height=float(layout["screen"]["height"]),
        unit=layout["screen"].get("unit", "dp"),
    )
    elements = tuple(
        Element(
            id=str(e["id"]),
            role=e["role"],
            x=float(e["x"]),
            y=float(e["y"]),
            w=float(e["w"]),
            h=float(e["h"]),
            group=e.get("group"),
            weight=e.get("weight", "equal"),
        )
        for e in layout.get("elements", [])
    )
    parsed = Layout(screen=screen, elements=elements, source=layout.get("source", "description-estimated"))
    report = check_layout(parsed)
    return {
        "source": report.source,
        "counts_by_severity": report.counts_by_severity,
        "findings": [asdict(f) for f in report.findings],
    }


# ============================================================================
# Tool 4 — platform_parity
# ============================================================================


@server.tool()
def lumo_parity_diff(
    android: dict[str, Any],
    ios: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Diff an Android (dp) and iOS (pt) layout, optionally against a design system.

    Compares the two layouts for component presence and sizing mismatches.
    Whitelists known platform-specific defaults (Material 48dp vs Apple HIG
    44pt touch target; Material bottom nav 80dp vs iOS Tab Bar 49pt) and
    reports them as `info`, not as mismatches.

    Reminder: dp and pt are both density-independent and equal in physical
    size on screen. 16dp matches 16pt. The classic "iOS uses 3× because
    Retina" misconception (writing 48pt on iOS for 16dp Android) is exactly
    the bug this tool catches.

    Args:
        android: Android layout JSON (same schema as lumo_theory_check)
        ios: iOS layout JSON
        config: Optional design-system config with `spacing`, `sizing`,
                `colors` token maps

    Returns:
        Dict with `confidence`, `android_source`, `ios_source`,
        `counts_by_severity`, and `findings` list.
    """

    def _to_layout(data: dict[str, Any]) -> Layout:
        screen = Screen(
            width=float(data["screen"]["width"]),
            height=float(data["screen"]["height"]),
            unit=data["screen"].get("unit", "dp"),
        )
        elements = tuple(
            Element(
                id=str(e["id"]),
                role=e["role"],
                x=float(e["x"]),
                y=float(e["y"]),
                w=float(e["w"]),
                h=float(e["h"]),
                group=e.get("group"),
                weight=e.get("weight", "equal"),
            )
            for e in data.get("elements", [])
        )
        return Layout(screen=screen, elements=elements, source=data.get("source", "description-estimated"))

    android_layout = _to_layout(android)
    ios_layout = _to_layout(ios)

    ds_config = None
    if config is not None:
        ds_config = DesignSystemConfig(
            spacing=config.get("spacing", {}),
            sizing=config.get("sizing", {}),
            colors=config.get("colors", {}),
        )

    report = diff(android_layout, ios_layout, ds_config)
    return {
        "confidence": report.confidence,
        "android_source": report.android_source,
        "ios_source": report.ios_source,
        "counts_by_severity": report.counts_by_severity,
        "findings": [asdict(f) for f in report.findings],
    }


# ============================================================================
# Tool 5 — source_check_compose
# ============================================================================


@server.tool()
def lumo_source_check_compose(
    source: str,
    path: str = "<source>",
    spacing_scale: list[float] | None = None,
    radius_scale: list[float] | None = None,
) -> dict[str, Any]:
    """AST-based design-system drift checks on a Compose .kt source string.

    Parses the source with tree-sitter-kotlin and walks Modifier chains,
    Color() constructors, and RoundedCornerShape declarations. Flags only
    *hardcoded* literals — token references like MaterialTheme.spacing.md
    or MaterialTheme.colorScheme.primary are intentionally skipped, so this
    tool catches drift without nagging about valid theme usage.

    Reports four checks:
      - undersized_tap_target (a11y) — Modifier.size(N.dp) with N < 48
      - off_scale_spacing    (consistency) — padding not on the scale
      - hardcoded_color      (token)       — Color(0xFFRRGGBB) literals
      - off_scale_radius     (consistency) — RoundedCornerShape off scale

    All findings carry source="code-estimated" — the parser is exact, but
    runtime values cannot be resolved statically, so the confidence label
    stays honest about the input shape.

    Args:
        source: Compose .kt source code (full file content).
        path: Optional path label used in finding locations.
        spacing_scale: Optional spacing scale in dp. Defaults to the
                       Material 3 / HIG-flavoured scale.
        radius_scale: Optional radius scale in dp. Defaults to Material 3.

    Returns:
        Dict with `file`, `language`, `counts_by_severity`,
        `counts_by_category`, and `findings` list.
    """
    report = check_compose(
        source,
        path=path,
        spacing_scale=tuple(spacing_scale) if spacing_scale else DEFAULT_SPACING_SCALE_DP,
        radius_scale=tuple(radius_scale) if radius_scale else DEFAULT_RADIUS_SCALE_DP,
    )
    return {
        "file": report.file,
        "language": report.language,
        "counts_by_severity": report.counts_by_severity,
        "counts_by_category": report.counts_by_category,
        "findings": [asdict(f) for f in report.findings],
    }


# ============================================================================
# Tool 6 — source_check_swiftui
# ============================================================================


@server.tool()
def lumo_source_check_swiftui(
    source: str,
    path: str = "<source>",
    spacing_scale: list[float] | None = None,
    radius_scale: list[float] | None = None,
) -> dict[str, Any]:
    """AST-based design-system drift checks on a SwiftUI .swift source string.

    Parses the source with tree-sitter-swift and walks chained modifiers,
    `Color(red:green:blue:)` constructors, and `.cornerRadius(...)` calls.
    Flags only *hardcoded* literals — token references (`Theme.spacing.md`,
    asset-catalog `Color("brandPrimary")`, named constants `Color.red`)
    are intentionally skipped to catch drift without nagging valid usage.

    Reports four checks (HIG-tuned where relevant):
      - undersized_tap_target (a11y) — `.frame(width:N, height:N)` with
        both N < 44pt (Apple HIG minimum, not Material 48dp).
      - off_scale_spacing    (consistency) — `.padding(N)` or
        `.padding(<edge>, N)` where N is not on the spacing scale.
      - hardcoded_color      (token)       — `Color(red:green:blue:)`
        with all three channels numeric.
      - off_scale_radius     (consistency) — `.cornerRadius(N)` off scale.

    All findings carry source="code-estimated" — the parser is exact, but
    runtime values cannot be resolved statically, so the confidence label
    stays honest about the input shape.

    The same spacing/radius defaults apply to SwiftUI and Compose because
    dp and pt are physically equal: 16dp ≡ 16pt on screen. Use a custom
    scale only if your design system explicitly differs across platforms.

    Args:
        source: SwiftUI .swift source code (full file content).
        path: Optional path label used in finding locations.
        spacing_scale: Optional spacing scale in pt. Defaults to the
                       Material 3 / HIG-flavoured scale.
        radius_scale: Optional radius scale in pt. Defaults to Material 3.

    Returns:
        Dict with `file`, `language`, `counts_by_severity`,
        `counts_by_category`, and `findings` list.
    """
    report = check_swiftui(
        source,
        path=path,
        spacing_scale=tuple(spacing_scale) if spacing_scale else DEFAULT_SPACING_SCALE_DP,
        radius_scale=tuple(radius_scale) if radius_scale else DEFAULT_RADIUS_SCALE_DP,
    )
    return {
        "file": report.file,
        "language": report.language,
        "counts_by_severity": report.counts_by_severity,
        "counts_by_category": report.counts_by_category,
        "findings": [asdict(f) for f in report.findings],
    }


# ============================================================================
# Tool 7 — audit_scan
# ============================================================================


@server.tool()
def lumo_audit_scan(
    root: str,
    spacing_scale: list[float] | None = None,
    radius_scale: list[float] | None = None,
    exclude: list[str] | None = None,
    top_n_values: int = 15,
) -> dict[str, Any]:
    """Whole-repository design-system audit for Compose + SwiftUI.

    Walks every `.kt` / `.kts` / `.swift` file under `root`, runs the
    `lumo.source` checks per file, and aggregates two views:

      1. Drift hotspots — counts of findings by check, category,
         severity, and language. Use this to prioritise refactors.

      2. Measured scale — frequency tables of every hardcoded padding /
         radius / size literal in the codebase. Compare the top values
         against your configured scale to see actual drift (not just
         rule violations on individual lines).

    Hardcoded skip directories (`.git`, `build`, `node_modules`, `Pods`,
    `DerivedData`, `.gradle`, `dist`, `out`, etc.) are always excluded
    so the scan stays fast and signal-rich. Pass additional POSIX-style
    globs in `exclude` for project-specific filters.

    Token references (`MaterialTheme.spacing.md`, `Theme.colours.brand`,
    `Color("brandPrimary")`) are intentionally invisible to the audit —
    we count *hardcoded* literals only. Same honesty rule as `lumo-source`.

    Args:
        root: Absolute path to the repo root to scan.
        spacing_scale: Optional spacing scale in dp/pt. Defaults to the
                       Material 3 / HIG-flavoured scale.
        radius_scale: Optional radius scale in dp/pt. Defaults to Material 3.
        exclude: Extra POSIX-style globs (relative to `root`) to skip
                 on top of the always-skipped directories.
        top_n_values: How many top-frequency values per kind to surface.

    Returns:
        Dict with `root`, `files_scanned`, `files_with_findings`,
        `total_findings`, `counts_by_*`, `findings`, and
        `scale_observations`.
    """
    config = AuditConfig(
        spacing_scale=tuple(spacing_scale) if spacing_scale else DEFAULT_SPACING_SCALE_DP,
        radius_scale=tuple(radius_scale) if radius_scale else DEFAULT_RADIUS_SCALE_DP,
        extra_excludes=tuple(exclude) if exclude else (),
        top_n_values=top_n_values,
    )
    report = scan_repo(root, config=config)
    return {
        "root": report.root,
        "files_scanned": report.files_scanned,
        "files_with_findings": report.files_with_findings,
        "total_findings": report.total_findings,
        "counts_by_severity": report.counts_by_severity,
        "counts_by_category": report.counts_by_category,
        "counts_by_check": report.counts_by_check,
        "counts_by_language": report.counts_by_language,
        "findings": [asdict(f) for f in report.findings],
        "scale_observations": [
            {
                "kind": obs.kind,
                "total_literals": obs.total_literals,
                "values_by_frequency": [
                    {"value": v, "count": c} for v, c in obs.values_by_frequency
                ],
                "on_scale": list(obs.on_scale),
                "off_scale": list(obs.off_scale),
            }
            for obs in report.scale_observations
        ],
    }


# ============================================================================
# Entrypoint
# ============================================================================


def main() -> None:
    """Run the Lumo MCP server over stdio (the MCP standard for local tools)."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
