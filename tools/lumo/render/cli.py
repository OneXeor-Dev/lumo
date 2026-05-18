"""CLI for lumo-render — AST layout evaluator for Jetpack Compose.

Usage:
    lumo-render compose --file Screen.kt
    lumo-render compose --file Screen.kt --target LoginScreen
    lumo-render compose --file Screen.kt --screen-width 411 --screen-height 891
    lumo-render compose --file Screen.kt --json
    lumo-render compose --file Screen.kt --out screen.json
    lumo-render compose --file - < Screen.kt   # read from stdin

Output is a Lumo-schema layout JSON ready to feed
`lumo-theory check --from` and `lumo-parity diff --from`. Every
element carries `source: "ast-resolved"` or `"ast-unresolved"` with a
`reason` — we never invent coordinates we cannot statically derive.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lumo.render.core import (
    DEFAULT_SCREEN_HEIGHT_DP,
    DEFAULT_SCREEN_WIDTH_DP,
    RenderReport,
    render_compose,
)


def _read_source(file_arg: str) -> str:
    if file_arg == "-":
        return sys.stdin.read()
    p = Path(file_arg)
    if not p.is_file():
        raise SystemExit(f"file not found: {file_arg}")
    return p.read_text(encoding="utf-8")


def _render_text(report: RenderReport) -> str:
    """Human-readable summary — one line per element."""
    lines: list[str] = []
    lines.append(
        f"screen {report.screen_width:g}x{report.screen_height:g}{report.unit}  "
        f"elements={len(report.elements)}  "
        f"resolved={report.resolved_count}  unresolved={report.unresolved_count}  "
        f"coverage={report.coverage:.0%}"
    )
    for e in report.elements:
        if e.source == "ast-resolved":
            lines.append(
                f"  {e.id:<28} {e.role:<16} "
                f"x={e.x:.1f} y={e.y:.1f} w={e.w:.1f} h={e.h:.1f}"
            )
        else:
            lines.append(
                f"  {e.id:<28} {e.role:<16} UNRESOLVED — {e.reason}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lumo-render",
        description=(
            "AST layout evaluator — produces Lumo-schema layout JSON from "
            "Compose source without running the app or any snapshot test."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    compose = sub.add_parser("compose", help="Render a @Composable function to layout JSON.")
    compose.add_argument(
        "--file",
        required=True,
        help="Path to a .kt source file, or '-' to read from stdin.",
    )
    compose.add_argument(
        "--target",
        default=None,
        help=(
            "Name of the @Composable to render. If omitted, the first "
            "@Composable in the file is used."
        ),
    )
    compose.add_argument(
        "--screen-width",
        type=float,
        default=DEFAULT_SCREEN_WIDTH_DP,
        help=f"Screen width in dp (default {DEFAULT_SCREEN_WIDTH_DP:g}). "
             f"Used to resolve fillMaxWidth() / weight() against the root frame.",
    )
    compose.add_argument(
        "--screen-height",
        type=float,
        default=DEFAULT_SCREEN_HEIGHT_DP,
        help=f"Screen height in dp (default {DEFAULT_SCREEN_HEIGHT_DP:g}).",
    )
    compose.add_argument(
        "--json",
        action="store_true",
        help="Emit Lumo-schema layout JSON to stdout instead of human-readable text.",
    )
    compose.add_argument(
        "--out",
        default=None,
        help="Also write the layout JSON to this file (always JSON, regardless of --json).",
    )

    args = parser.parse_args(argv)

    if args.cmd == "compose":
        source = _read_source(args.file)
        report = render_compose(
            source,
            target=args.target,
            screen_width=args.screen_width,
            screen_height=args.screen_height,
        )
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(_render_text(report))
        if args.out:
            Path(args.out).write_text(
                json.dumps(report.to_dict(), indent=2), encoding="utf-8"
            )
        # Exit codes: 0 if anything resolved, 2 if 0 elements (likely the
        # file had no @Composable). Coverage of 0 still exits 0 — the user
        # asked us to render, we rendered (everything unresolved is a valid
        # result, not an error).
        return 0 if report.elements else 2

    return 2


if __name__ == "__main__":
    sys.exit(main())
