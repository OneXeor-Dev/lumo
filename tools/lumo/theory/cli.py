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
    return _layout_from_dict(json.loads(raw))


def _layout_from_dict(data: dict[str, Any]) -> Layout:
    """Build a Layout from a parsed JSON payload.

    Elements with `source == "ast-unresolved"` or any missing coordinate
    are dropped silently — theory_check needs measured-or-resolved
    geometry to run Fitts / Hick / Gestalt. They are NOT errors; they
    are honest acknowledgement that `lumo-render` could not derive the
    value statically. The dropped count is exposed via `report.source`
    suffix downstream if needed.
    """
    screen = Screen(
        width=float(data["screen"]["width"]),
        height=float(data["screen"]["height"]),
        unit=data["screen"].get("unit", "dp"),
    )
    elements_list: list[Element] = []
    for e in data.get("elements", []):
        if e.get("source") == "ast-unresolved":
            continue
        if any(e.get(k) is None for k in ("x", "y", "w", "h")):
            continue
        elements_list.append(
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
        )
    return Layout(
        screen=screen,
        elements=tuple(elements_list),
        source=data.get("source", "description-estimated"),
    )


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
    group = check.add_mutually_exclusive_group(required=True)
    group.add_argument("--layout", help="Path to layout JSON, or '-' for stdin.")
    group.add_argument(
        "--from",
        dest="from_dir",
        help=(
            "Directory of layout JSON files (e.g. `build/lumo/` output of "
            "`lumo-render compose --out`). Every *.json is checked in turn; "
            "`ast-unresolved` elements are skipped per the honesty rule."
        ),
    )
    check.add_argument("--json", action="store_true", help="Emit JSON.")
    check.add_argument(
        "--platform",
        choices=["android", "ios"],
        default=None,
        help=(
            "Override the screen unit before checks. `android` forces dp + "
            "48dp Material tap target; `ios` forces pt + 44pt Apple HIG. "
            "Without this flag we trust the layout JSON's `screen.unit` "
            "field. Useful when rendering a Figma frame (which defaults to "
            "dp regardless of platform) and you want to apply HIG instead."
        ),
    )

    args = parser.parse_args(argv)

    if args.cmd == "check":
        if args.from_dir:
            return _run_from_dir(args.from_dir, json_output=args.json, platform=args.platform)
        layout = _load_layout(args.layout)
        if args.platform:
            layout = _override_platform(layout, args.platform)
        report = check_layout(layout)
        if args.json:
            _print_json(report)
        else:
            _print_human(report)
        return 0 if not report.findings else 1

    return 2


def _override_platform(layout: Layout, platform: str) -> Layout:
    """Rebuild a Layout with a forced unit per the user's --platform flag.

    Coordinates are NOT scaled — we trust that dp and pt are physically
    equal on screen (which they are, both density-independent). Only
    the unit label changes, which in turn drives `Screen.min_tap_target`
    via `unit == "dp"` returning 48dp vs `"pt"` returning 44pt.
    """
    unit: Any = "dp" if platform == "android" else "pt"
    new_screen = Screen(width=layout.screen.width, height=layout.screen.height, unit=unit)
    return Layout(screen=new_screen, elements=layout.elements, source=layout.source)


def _run_from_dir(dir_path: str, *, json_output: bool, platform: str | None = None) -> int:
    """Run theory_check against every layout JSON in a directory.

    Returns 0 if no file had findings, 1 if any file did, 2 if the
    directory was empty / unreadable.
    """
    root = Path(dir_path)
    if not root.is_dir():
        raise SystemExit(f"--from path is not a directory: {dir_path}")
    files = sorted(root.glob("*.json"))
    if not files:
        print(f"WARN  no *.json files in {dir_path}", file=sys.stderr)
        return 2

    any_findings = False
    aggregated: list[dict[str, Any]] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            layout = _layout_from_dict(data)
        except (KeyError, ValueError) as exc:
            print(f"SKIP  {f.name}: {exc}", file=sys.stderr)
            continue
        if platform:
            layout = _override_platform(layout, platform)
        report = check_layout(layout)
        if json_output:
            aggregated.append({
                "file": f.name,
                "source": report.source,
                "counts_by_severity": report.counts_by_severity,
                "findings": [asdict(x) for x in report.findings],
            })
        else:
            print(f"=== {f.name} ===")
            _print_human(report)
            print()
        if report.findings:
            any_findings = True

    if json_output:
        print(json.dumps(aggregated, indent=2))
    return 1 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main())
