"""Lumo MCP server.

Exposes every Lumo tool over the Model Context Protocol so any
MCP-compatible client (Claude Code, Cursor, Continue, Aider, Goose,
Zed, etc.) can call them with structured arguments.

Registered functions:
  - lumo_wcag_check / lumo_wcag_fix          (WCAG + OKLCH)
  - lumo_theory_check                        (Fitts / Hick / Gestalt)
  - lumo_parity_diff                         (cross-platform diff)
  - lumo_source_check_compose / _swiftui     (per-file AST drift)
  - lumo_audit_scan                          (whole-repo aggregator)
  - lumo_figma_diff                          (Figma token diff)
  - lumo_figma_render                        (Figma frame → measured layout JSON)
  - lumo_render_compose / _swiftui           (AST layout evaluator)

This is a thin wrapper over the existing Python API — the heavy lifting
stays in lumo.{wcag,theory,parity,source,audit,figma,render}. Adding MCP
did not change a single line of those modules.

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
from lumo.figma.core import (
    FigmaApiError,
    diff_against_audit as figma_diff_against_audit,
    fetch_node_layout as figma_fetch_node_layout,
    fetch_tokens as figma_fetch_tokens,
)
from lumo.parity.core import DesignSystemConfig, diff
from lumo.render.core import (
    DEFAULT_SCREEN_HEIGHT_DP,
    DEFAULT_SCREEN_WIDTH_DP,
    render_compose,
    render_swiftui,
)
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
# Tool 8 — figma_diff
# ============================================================================


@server.tool()
def lumo_figma_diff(
    file_key: str,
    audit_payload: dict[str, Any],
    mode: str | None = None,
    missing_threshold: int = 3,
) -> dict[str, Any]:
    """Diff a Figma file's COLOR + FLOAT variables against a code audit.

    Compares Figma design tokens against the *measured* spacing / radius /
    size scale and hardcoded colours that `lumo_audit_scan` already
    produced. Three buckets in the result:

      - **matched** — token value present in Figma and in code (with
        per-token occurrence count from the audit).
      - **unused_in_code** — Figma token never literal-used in code.
        Note: a token may still be used via theme indirection
        (`MaterialTheme.colorScheme.*`, `LocalDimensions.*`) without
        appearing here — so treat the list as candidates for review,
        not a hit-list for deletion.
      - **missing_from_figma** — hex / numeric value used at least
        `missing_threshold` times in code with no matching Figma token.
        Candidates for promotion to the design system.

    Matching is by VALUE, not name. Naming conventions drift across
    Figma / Compose / SwiftUI, so the only stable join key is the
    resolved hex or number. Token name appears in the report for human
    reference, never as a match key.

    Auth: requires `FIGMA_TOKEN` in the process environment. No way to
    pass the token via this MCP call by design — keeps secrets out of
    tool-call logs.

    Args:
        file_key: Figma file key (`abc123` from a Figma URL).
        audit_payload: JSON payload produced by `lumo_audit_scan` or the
            `lumo-audit scan --json` CLI.
        mode: Variable-collection mode name (e.g. "Dark"). When None
            (default), each collection's default mode is used.
        missing_threshold: Minimum code occurrences before a value is
            flagged as missing from Figma. Default 3.

    Returns:
        Dict with `file_key`, `mode_label`, `summary_counts` (matched /
        unused_in_code / missing_from_figma), three lists for each
        bucket, and `figma_token_counts` per type.
    """
    figma = figma_fetch_tokens(file_key, mode=mode)
    report = figma_diff_against_audit(
        figma,
        audit_payload,
        missing_threshold=missing_threshold,
    )
    return {
        "file_key": report.file_key,
        "mode_label": report.mode_label,
        "summary_counts": dict(report.summary_counts),
        "matched": [
            {
                "token": {
                    "id": m.token.id,
                    "name": m.token.name,
                    "type": m.token.type,
                    "collection": m.token.collection,
                    "mode_name": m.token.mode_name,
                    "value": m.token.value_canonical,
                    "is_alias_resolved": m.token.is_alias_resolved,
                },
                "code_kind": m.code_kind,
                "code_occurrences": m.code_occurrences,
            }
            for m in report.matched
        ],
        "unused_in_code": [
            {
                "token": {
                    "id": u.token.id,
                    "name": u.token.name,
                    "type": u.token.type,
                    "collection": u.token.collection,
                    "mode_name": u.token.mode_name,
                    "value": u.token.value_canonical,
                    "is_alias_resolved": u.token.is_alias_resolved,
                },
            }
            for u in report.unused_in_code
        ],
        "missing_from_figma": [
            {
                "value": m.value,
                "code_kind": m.code_kind,
                "code_occurrences": m.code_occurrences,
            }
            for m in report.missing_from_figma
        ],
        "figma_token_counts": {
            "COLOR": len(figma.colors),
            "FLOAT": len(figma.floats),
            "STRING": len(figma.strings),
            "BOOLEAN": len(figma.booleans),
        },
    }


# ============================================================================
# Tool 9 — figma_render
# ============================================================================


@server.tool()
def lumo_figma_render(
    file_key: str,
    node_id: str,
    screen_width: float | None = None,
    screen_height: float | None = None,
) -> dict[str, Any]:
    """Render a Figma frame to a Lumo layout JSON — `source: "measured"`.

    Hits Figma's `/v1/files/{file_key}/nodes?ids={node_id}` REST
    endpoint, walks the returned subtree, and emits the same Lumo
    layout JSON schema `lumo_theory_check` and `lumo_parity_diff`
    already consume. Every element carries `source: "measured"` —
    Figma's `absoluteBoundingBox` is the rendered coordinate after
    Auto-Layout and constraints resolve, so this is honest measurement,
    not a static guess.

    Use this tool when the user wants to audit the **design itself**
    (Fitts / Hick / Gestalt / reach checks on a Figma frame) before
    any code ships. Pair with `lumo_theory_check` for cognitive-science
    findings on the resulting JSON.

    Element ids come from Figma layer names (sanitised — spaces and
    punctuation become underscores). Role heuristics from layer-name
    prefixes: `btn_*` → `primary_action`, `nav_*` → `nav_item`,
    `icon_*` → `icon`, `input_*`/`*field*` → `input`; TEXT nodes →
    `text`; RECTANGLE/VECTOR/ELLIPSE → `image`; otherwise `decorative`.
    Users override by renaming layers.

    Auth: reads `FIGMA_TOKEN` from the environment. Never accept the
    token via this argument — env-only convention shared with
    `lumo_figma_diff`.

    Honesty rules:
      - Hidden layers (`visible: false`) are skipped.
      - Nodes without `absoluteBoundingBox` (auto-layout placeholders
        Figma hasn't measured yet) are skipped, not faked.
      - Element count + coordinates come directly from the API — we
        never invent numbers.

    Args:
        file_key: Figma file key (the `abc123` part of a Figma URL).
        node_id: Figma node id (e.g. `1:23`). Get it from the URL's
                 `node-id=` query param (Figma uses `1-23` there;
                 either form is accepted).
        screen_width: Optional clamp on the root frame width. Default:
                      use Figma's own frame width.
        screen_height: Optional clamp on the root frame height.

    Returns:
        Dict matching the Lumo layout JSON schema — same shape as
        `lumo_render_compose` / `lumo_render_swiftui`, with
        `source: "measured"` everywhere.
    """
    report = figma_fetch_node_layout(
        file_key,
        node_id.replace("-", ":"),
        screen_width=screen_width,
        screen_height=screen_height,
    )
    return report.to_dict()


# ============================================================================
# Tool 10 — render_compose
# ============================================================================


@server.tool()
def lumo_render_compose(
    source: str,
    target: str | None = None,
    screen_width: float = DEFAULT_SCREEN_WIDTH_DP,
    screen_height: float = DEFAULT_SCREEN_HEIGHT_DP,
) -> dict[str, Any]:
    """AST layout evaluator for Jetpack Compose — produces measured-like
    (x, y, w, h) coordinates from source, no build / app run / snapshot test.

    Walks the same tree-sitter-kotlin AST `lumo_source_check_compose` uses,
    but instead of running drift checks it *evaluates* the layout: an
    offset-stack interpreter for `Column` / `Row` / `Box` / `Card` /
    `Surface` and the common modifier transforms (`padding(...)` in every
    form, `size`/`width`/`height`, `fillMaxWidth/Height/Size`,
    `offset(x, y)`, `weight(N)` two-pass, `wrapContentSize`, `testTag`)
    produces coordinates for every element it can derive statically.

    Output is the same Lumo layout JSON `lumo_theory_check` and
    `lumo_parity_diff` consume, so this is the missing piece that lets
    those tools run on a typical screen without hand-built JSON. Pipeline:

        lumo_render_compose(src) → layout JSON → lumo_theory_check(layout)

    Honesty hierarchy — every element carries one of these `source` labels:

        measured > ast-resolved > code-estimated > description-estimated

      - `ast-resolved` — value derived from a static AST evaluation of
        known layout rules. Higher trust than `code-estimated` (which
        means "the LLM guessed numbers from reading code") because the
        evaluator is deterministic and refuses to invent values.
      - `ast-unresolved` — token reference (`MaterialTheme.spacing.md`),
        unknown composable, runtime expression, or a descendant of an
        unresolved container. Carries a `reason` field, no coordinates.
        Sibling elements are NOT tainted by an unresolved sibling.

    Atoms supported in v1: Text, Button (+ outlined/text/elevated/tonal
    variants), IconButton (+ filled/tonal/outlined variants), Icon, Image,
    FloatingActionButton (+ small/large/extended), Spacer.

    Args:
        source: Compose .kt source code (full file content).
        target: Optional name of the @Composable to render. If omitted,
                the first @Composable in the file is used.
        screen_width: Root container width in dp (default 360).
                      `fillMaxWidth()` / `weight(N)` resolve against this.
        screen_height: Root container height in dp (default 800).

    Returns:
        Dict matching the Lumo layout JSON schema:
          - `screen` — width / height / unit ("dp")
          - `source` — top-level label ("ast-resolved")
          - `elements` — list of {id, role, source, x?, y?, w?, h?, reason?}
          - `coverage` — fraction of elements that resolved (0.0–1.0)
    """
    report = render_compose(
        source,
        target=target,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    return report.to_dict()


# ============================================================================
# Tool 10 — render_swiftui
# ============================================================================


@server.tool()
def lumo_render_swiftui(
    source: str,
    target: str | None = None,
    screen_width: float = DEFAULT_SCREEN_WIDTH_DP,
    screen_height: float = DEFAULT_SCREEN_HEIGHT_DP,
) -> dict[str, Any]:
    """AST layout evaluator for SwiftUI — same evaluator as Compose, plugged
    into a SwiftUI-specific parser.

    Walks the tree-sitter-swift AST of a SwiftUI source string and
    produces measured-like coordinates for every view it can derive
    statically. Containers: `VStack` / `HStack` / `ZStack` / `Group`.
    Atoms: `Text`, `Button`, `Image`, `Label`, `Spacer`, `Rectangle`,
    `Circle`, `RoundedRectangle`, `Divider`, `Toggle`, `NavigationLink`,
    `Link`. Modifiers: `.padding()` in every form (no-arg / value / edge
    + value covering `.horizontal` / `.vertical` / `.leading` /
    `.trailing` / `.top` / `.bottom` / `.all`), `.frame(width:height:)`,
    `.frame(maxWidth: .infinity)` as fill-max marker, `.offset(x:y:)`,
    `.accessibilityIdentifier("id")`.

    `Spacer()` with no `.frame` acts as axis-flex inside an HStack /
    VStack — same two-pass allocation as Compose's `weight(N)`.

    Apple HIG defaults baked in: 44 pt minimum tap target for `Button` /
    `NavigationLink` / `Toggle`, 24 pt for `Image`.

    Output schema is identical to `lumo_render_compose`. Coordinates are
    unit-less floats; the `screen.unit` is `"pt"` so downstream parity
    tools can tell the platforms apart, but pt and dp are physically
    equal so direct comparison is valid — the same logical screen
    expressed in Compose and SwiftUI yields matching topology.

    Same honesty hierarchy as Compose:

        measured > ast-resolved > code-estimated > description-estimated

    Args:
        source: SwiftUI .swift source code (full file content).
        target: Optional name of the View struct to render (e.g.
                "LoginView"). If omitted, the first View is used.
        screen_width: Root container width in pt (default 360).
                      `.frame(maxWidth: .infinity)` resolves against this.
        screen_height: Root container height in pt (default 800).

    Returns:
        Dict matching the Lumo layout JSON schema (same shape as
        `lumo_render_compose`).
    """
    report = render_swiftui(
        source,
        target=target,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    return report.to_dict()


# ============================================================================
# Entrypoint
# ============================================================================


def main() -> None:
    """Run the Lumo MCP server over stdio (the MCP standard for local tools)."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
