"""CLI entrypoint for the WCAG validator. Invoked by the Lumo skill or by the user.

Examples:
    lumo-wcag check --fg "#3B82F6" --bg "#FFFFFF"
    lumo-wcag check --fg "#3B82F6" --bg "#FFFFFF" --level AAA --size normal
    lumo-wcag fix   --fg "#3B82F6" --bg "#FFFFFF" --level AA  --size normal
    lumo-wcag check --fg "#3B82F6" --bg "#FFFFFF" --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Any

from lumo.wcag.core import auto_correct, check_pair


def _print_check(result: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(result), indent=2))
        return
    status = "PASS" if result.passes else "FAIL"
    print(
        f"{status}  {result.fg} on {result.bg}  "
        f"ratio={result.ratio}:1  required={result.required}:1  "
        f"({result.level}, {result.size} text)"
    )


def _print_fix(result: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(result), indent=2, default=str))
        return
    if result.strategy == "unchanged":
        print(
            f"PASS  {result.original.fg} on {result.original.bg}  "
            f"ratio={result.original.ratio}:1  (no change needed)"
        )
        return
    print(
        f"FIXED  {result.original.fg} → {result.corrected_fg}  on {result.corrected_bg}\n"
        f"       ratio {result.original.ratio}:1 → {result.corrected.ratio}:1  "
        f"(required {result.corrected.required}:1)\n"
        f"       strategy={result.strategy}  iterations={result.iterations}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lumo-wcag",
        description="WCAG contrast validator with OKLCH auto-correct.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    def _add_pair_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--fg", required=True, help="Foreground hex (#RGB, #RRGGBB, #RGBA, #RRGGBBAA)")
        p.add_argument("--bg", required=True, help="Background hex")
        p.add_argument("--level", choices=["AA", "AAA"], default="AA")
        p.add_argument("--size", choices=["normal", "large"], default="normal")
        p.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text")

    check = sub.add_parser("check", help="Check whether a color pair passes WCAG")
    _add_pair_args(check)

    fix = sub.add_parser("fix", help="Auto-correct a failing pair by adjusting the foreground")
    _add_pair_args(fix)
    fix.add_argument("--max-iterations", type=int, default=60)

    args = parser.parse_args(argv)

    if args.cmd == "check":
        check_result = check_pair(args.fg, args.bg, args.level, args.size)
        _print_check(check_result, args.json)
        return 0 if check_result.passes else 1

    if args.cmd == "fix":
        fix_result = auto_correct(args.fg, args.bg, args.level, args.size, args.max_iterations)
        _print_fix(fix_result, args.json)
        return 0 if fix_result.corrected.passes else 2

    return 2


if __name__ == "__main__":
    sys.exit(main())
