"""CLI for theory_check.

Usage:
    lumo-theory check --layout path/to/layout.json [--json]
    cat layout.json | lumo-theory check --layout - [--json]

Layout JSON schema (see SKILL.md for full spec):
{
  "screen":  { "width": 411, "height": 891, "unit": "dp" },
  "source":  "measured" | "code-estimated" | "description-estimated",
  "elements": [
    {
      "id": "btn_continue",
      "role": "primary_action",
      "x": 24, "y": 800, "w": 363, "h": 56,
      "group": "form_actions",
      "weight": "primary"
    },
    ...
  ]
}
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lumo.theory.core import Element, Layout, Screen, check_layout


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


def _print_human(report: Any) -> None:
    if not report.findings:
        print("OK  no theory_check findings.")
        print(f"    source: {report.source}")
        return

    counts = report.counts_by_severity
    severity_summary = ", ".join(
        f"{n} {sev}" for sev, n in sorted(counts.items(), key=lambda x: x[0])
    )
    print(f"FOUND  {len(report.findings)} findings ({severity_summary})")
    print(f"       source: {report.source}\n")

    for i, f in enumerate(report.findings, 1):
        elements = ", ".join(f.elements)
        print(f"  {i}. [{f.severity.upper():8}] {f.check}")
        print(f"     elements: {elements}")
        print(f"     {f.message}")
        print(f"     → {f.recommendation}")
        if f.metric:
            metric_str = ", ".join(f"{k}={v:.2f}" for k, v in f.metric.items())
            print(f"     metric: {metric_str}")
        print()


def _print_json(report: Any) -> None:
    payload = {
        "source": report.source,
        "counts_by_severity": report.counts_by_severity,
        "findings": [asdict(f) for f in report.findings],
    }
    print(json.dumps(payload, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lumo-theory",
        description="Cognitive-science layout checks for mobile UI.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Check a layout against Fitts / Hick / Gestalt / Reach.")
    check.add_argument("--layout", required=True, help="Path to layout JSON, or '-' for stdin.")
    check.add_argument("--json", action="store_true", help="Emit JSON.")

    args = parser.parse_args(argv)

    if args.cmd == "check":
        layout = _load_layout(args.layout)
        report = check_layout(layout)
        if args.json:
            _print_json(report)
        else:
            _print_human(report)
        return 0 if not report.findings else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
