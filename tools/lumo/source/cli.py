"""CLI for lumo-source — AST-based design-system drift checks.

Usage:
    lumo-source check --file path/to/Screen.kt
    lumo-source check --file - < Screen.kt
    lumo-source check --file Screen.kt --json
    lumo-source check --file Screen.kt --scale 0,4,8,12,16,24,32

Unlike lumo-theory / lumo-parity (which need a layout JSON), lumo-source
reads the actual Compose source and flags hardcoded values that the
layout-based checks cannot see: off-scale spacing, raw hex colours,
undersized tap targets, and off-scale corner radii.

Honesty rules (locked):
  - Token references (MaterialTheme.spacing.md, LocalDimensions, etc.)
    are NEVER flagged. We only catch hardcoded literals.
  - All findings carry source="code-estimated" — the parser is exact, but
    we cannot resolve runtime values, so the confidence label stays
    honest about the input shape.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from lumo.source.core import (
    DEFAULT_RADIUS_SCALE_DP,
    DEFAULT_SPACING_SCALE_DP,
    SourceReport,
    check_compose,
    check_swiftui,
)


def _detect_language(file_arg: str, override: str | None) -> str:
    """Return 'kotlin' or 'swift' based on the override or the path suffix."""
    if override:
        if override not in ("kotlin", "swift"):
            raise SystemExit(f"--lang must be 'kotlin' or 'swift', got: {override}")
        return override
    if file_arg == "-":
        raise SystemExit(
            "Reading from stdin requires --lang kotlin or --lang swift "
            "(cannot infer language from '-')."
        )
    lower = file_arg.lower()
    if lower.endswith(".kt") or lower.endswith(".kts"):
        return "kotlin"
    if lower.endswith(".swift"):
        return "swift"
    raise SystemExit(
        f"Cannot infer language from '{file_arg}'. "
        "Use --lang kotlin or --lang swift."
    )


def _parse_scale(text: str) -> tuple[float, ...]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("scale must be a non-empty comma-separated list of numbers")
    try:
        return tuple(float(p) for p in parts)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"scale contains a non-numeric value: {e}") from e


def _load_source(file_arg: str) -> tuple[str, str]:
    """Return (source_text, path_label) — reads stdin when file_arg == '-'."""
    if file_arg == "-":
        return sys.stdin.read(), "<stdin>"
    p = Path(file_arg)
    return p.read_text(encoding="utf-8"), str(p)


_LANG_DISPATCH = {
    "kotlin": check_compose,
    "swift": check_swiftui,
}


def _print_human(report: SourceReport) -> None:
    if not report.findings:
        print(f"OK  no source findings in {report.file}.")
        return

    counts = report.counts_by_severity
    severity_summary = ", ".join(
        f"{n} {sev}" for sev, n in sorted(counts.items(), key=lambda x: x[0])
    )
    print(f"FOUND  {len(report.findings)} findings ({severity_summary}) in {report.file}")
    print(f"       language: {report.language}\n")

    for i, f in enumerate(report.findings, 1):
        print(f"  {i}. [{f.severity.upper():8}] {f.check}  ({f.category})")
        print(f"     {f.file}:{f.line}:{f.column}")
        print(f"     {f.snippet}")
        print(f"     {f.message}")
        print(f"     → {f.recommendation}")
        print()


def _print_json(report: SourceReport) -> None:
    payload = {
        "file": report.file,
        "language": report.language,
        "counts_by_severity": report.counts_by_severity,
        "counts_by_category": report.counts_by_category,
        "findings": [asdict(f) for f in report.findings],
    }
    print(json.dumps(payload, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lumo-source",
        description="AST-based design-system drift checks for Compose / SwiftUI source.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser(
        "check",
        help="Check a Compose .kt or SwiftUI .swift file for design-system drift.",
    )
    check.add_argument(
        "--file",
        required=True,
        help="Path to a .kt / .kts / .swift file, or '-' for stdin.",
    )
    check.add_argument(
        "--lang",
        choices=("kotlin", "swift"),
        default=None,
        help=(
            "Force the language. Auto-detected from the file extension "
            "when omitted; required when reading from stdin."
        ),
    )
    check.add_argument(
        "--scale",
        type=_parse_scale,
        default=DEFAULT_SPACING_SCALE_DP,
        help=(
            "Comma-separated spacing scale in dp (default: "
            f"{','.join(str(int(v)) if v.is_integer() else str(v) for v in DEFAULT_SPACING_SCALE_DP)})."
        ),
    )
    check.add_argument(
        "--radius-scale",
        type=_parse_scale,
        default=DEFAULT_RADIUS_SCALE_DP,
        help=(
            "Comma-separated radius scale in dp (default: "
            f"{','.join(str(int(v)) if v.is_integer() else str(v) for v in DEFAULT_RADIUS_SCALE_DP)})."
        ),
    )
    check.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text.")

    args = parser.parse_args(argv)

    if args.cmd == "check":
        lang = _detect_language(args.file, args.lang)
        source, path_label = _load_source(args.file)
        report = _LANG_DISPATCH[lang](
            source,
            path=path_label,
            spacing_scale=args.scale,
            radius_scale=args.radius_scale,
        )
        if args.json:
            _print_json(report)
        else:
            _print_human(report)
        return 0 if not report.findings else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
