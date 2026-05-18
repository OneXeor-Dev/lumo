"""CLI for lumo-render — AST layout evaluator for Compose AND SwiftUI.

Usage:
    lumo-render compose --file Screen.kt
    lumo-render compose --file Screen.kt --target LoginScreen
    lumo-render compose --file Screen.kt --screen-width 411 --screen-height 891
    lumo-render compose --file Screen.kt --json
    lumo-render compose --file Screen.kt --out screen.android.json
    lumo-render compose --file - < Screen.kt   # read from stdin

    lumo-render swiftui --file LoginView.swift
    lumo-render swiftui --file LoginView.swift --target LoginView
    lumo-render swiftui --file LoginView.swift --out screen.ios.json

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
    render_swiftui,
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


def _add_common_args(p: argparse.ArgumentParser, *, file_help: str, target_help: str) -> None:
    p.add_argument("--file", required=True, help=file_help)
    p.add_argument("--target", default=None, help=target_help)
    p.add_argument(
        "--screen-width",
        type=float,
        default=DEFAULT_SCREEN_WIDTH_DP,
        help=f"Screen width (default {DEFAULT_SCREEN_WIDTH_DP:g}). "
             f"Used to resolve fillMax / weight / .frame(maxWidth: .infinity).",
    )
    p.add_argument(
        "--screen-height",
        type=float,
        default=DEFAULT_SCREEN_HEIGHT_DP,
        help=f"Screen height (default {DEFAULT_SCREEN_HEIGHT_DP:g}).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit Lumo-schema layout JSON to stdout instead of human-readable text.",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Also write the layout JSON to this file (always JSON, regardless of --json).",
    )


def _run(report: RenderReport, *, json_output: bool, out_path: str | None) -> int:
    if json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(_render_text(report))
    if out_path:
        Path(out_path).write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
    return 0 if report.elements else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lumo-render",
        description=(
            "AST layout evaluator — produces Lumo-schema layout JSON from "
            "Compose or SwiftUI source without running the app or any "
            "snapshot test."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    compose = sub.add_parser("compose", help="Render a @Composable function to layout JSON.")
    _add_common_args(
        compose,
        file_help="Path to a .kt source file, or '-' to read from stdin.",
        target_help=(
            "Name of the @Composable to render. If omitted, the first "
            "@Composable in the file is used."
        ),
    )

    swiftui = sub.add_parser("swiftui", help="Render a SwiftUI View struct to layout JSON.")
    _add_common_args(
        swiftui,
        file_help="Path to a .swift source file, or '-' to read from stdin.",
        target_help=(
            "Name of the View struct to render (e.g. 'LoginView'). If "
            "omitted, the first View in the file is used."
        ),
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
        return _run(report, json_output=args.json, out_path=args.out)

    if args.cmd == "swiftui":
        source = _read_source(args.file)
        report = render_swiftui(
            source,
            target=args.target,
            screen_width=args.screen_width,
            screen_height=args.screen_height,
        )
        return _run(report, json_output=args.json, out_path=args.out)

    return 2


if __name__ == "__main__":
    sys.exit(main())
