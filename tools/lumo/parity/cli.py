"""CLI for platform_parity.

Usage:
    lumo-parity diff --android <path|-> --ios <path|-> [--config <path>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lumo.parity.core import DesignSystemConfig, diff
from lumo.theory.core import Element, Layout, Screen


def _load_layout(source: str) -> Layout:
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw)
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


def _load_config(path: str) -> DesignSystemConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return DesignSystemConfig(
        spacing=data.get("spacing", {}),
        sizing=data.get("sizing", {}),
        colors=data.get("colors", {}),
    )


def _print_human(report: Any) -> None:
    if not report.findings:
        print("OK  Android and iOS layouts are in parity.")
        print(f"    confidence: {report.confidence}")
        print(f"    android: {report.android_source}, ios: {report.ios_source}")
        return

    counts = report.counts_by_severity
    severity_summary = ", ".join(
        f"{n} {sev}" for sev, n in sorted(counts.items(), key=lambda x: x[0])
    )
    print(f"FOUND  {len(report.findings)} parity findings ({severity_summary})")
    print(f"       confidence: {report.confidence}")
    print(f"       android: {report.android_source}, ios: {report.ios_source}\n")

    for i, f in enumerate(report.findings, 1):
        print(f"  {i}. [{f.severity.upper():8}] {f.check}")
        if f.element_id:
            print(f"     element: {f.element_id}")
        if f.android_value is not None or f.ios_value is not None:
            print(f"     android: {f.android_value}    ios: {f.ios_value}")
        print(f"     {f.message}")
        print(f"     → {f.recommendation}")
        print()


def _print_json(report: Any) -> None:
    payload = {
        "confidence": report.confidence,
        "android_source": report.android_source,
        "ios_source": report.ios_source,
        "counts_by_severity": report.counts_by_severity,
        "findings": [asdict(f) for f in report.findings],
    }
    print(json.dumps(payload, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lumo-parity",
        description="Cross-platform parity diff: Android (dp) vs iOS (pt).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diff", help="Diff two layouts and (optionally) validate against a design system.")
    d.add_argument("--android", required=True, help="Path to Android layout JSON, or '-' for stdin.")
    d.add_argument("--ios", required=True, help="Path to iOS layout JSON, or '-' for stdin.")
    d.add_argument("--config", default=None, help="Optional lumo.config.json with design tokens.")
    d.add_argument("--json", action="store_true", help="Emit JSON.")

    args = parser.parse_args(argv)

    if args.cmd == "diff":
        if args.android == "-" and args.ios == "-":
            print("error: cannot read both layouts from stdin", file=sys.stderr)
            return 2
        android = _load_layout(args.android)
        ios = _load_layout(args.ios)
        config = _load_config(args.config) if args.config else None
        report = diff(android, ios, config)
        if args.json:
            _print_json(report)
        else:
            _print_human(report)
        return 0 if not report.findings else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
