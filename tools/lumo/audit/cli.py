"""CLI for `lumo-audit` — whole-repo design-system audit.

Usage:
    lumo-audit scan --root path/to/repo
    lumo-audit scan --root . --exclude "tests/**" --exclude "samples/**"
    lumo-audit scan --root . --config lumo.config.json --json
    lumo-audit scan --root . --out report.md

Output contract:

  - Human-readable summary always goes to stdout.
  - Pass `--json` to emit JSON to stdout instead.
  - Pass `--out FILE.md` to also write a markdown report to disk. The
    summary still goes to stdout — the file is an additional channel,
    not a substitute.

Exit code is `0` when there are no findings, `1` otherwise. Mirrors the
other Lumo CLIs.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from lumo.audit.core import (
    AuditConfig,
    AuditReport,
    scan_repo,
)
from lumo.source.core import DEFAULT_RADIUS_SCALE_DP, DEFAULT_SPACING_SCALE_DP


def _parse_scale(text: str) -> tuple[float, ...]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("scale must be a non-empty comma-separated list of numbers")
    try:
        return tuple(float(p) for p in parts)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"scale contains a non-numeric value: {e}") from e


def _load_config_file(path: Path) -> dict[str, object]:
    """Read lumo.config.json and return its `audit` section (or {})."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"config file not found: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"config file is not valid JSON: {path}: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"config file must contain a JSON object: {path}")
    audit = data.get("audit", {})
    if not isinstance(audit, dict):
        raise SystemExit(f"config 'audit' must be a JSON object: {path}")
    assert isinstance(audit, dict)
    return audit


def _build_config(args: argparse.Namespace) -> AuditConfig:
    spacing_scale: tuple[float, ...] = DEFAULT_SPACING_SCALE_DP
    radius_scale: tuple[float, ...] = DEFAULT_RADIUS_SCALE_DP
    extra_excludes: tuple[str, ...] = ()
    top_n_values: int = 15

    if args.config:
        section = _load_config_file(Path(args.config))
        raw_spacing = section.get("spacing_scale")
        if isinstance(raw_spacing, list):
            spacing_scale = tuple(float(v) for v in raw_spacing)
        raw_radius = section.get("radius_scale")
        if isinstance(raw_radius, list):
            radius_scale = tuple(float(v) for v in raw_radius)
        raw_exclude = section.get("exclude")
        if isinstance(raw_exclude, list):
            extra_excludes = tuple(str(v) for v in raw_exclude)
        raw_top_n = section.get("top_n_values")
        if isinstance(raw_top_n, int):
            top_n_values = raw_top_n

    # CLI flags override config-file values.
    if args.scale is not None:
        spacing_scale = args.scale
    if args.radius_scale is not None:
        radius_scale = args.radius_scale
    if args.exclude:
        extra_excludes = extra_excludes + tuple(args.exclude)
    if args.top_n is not None:
        top_n_values = args.top_n

    return AuditConfig(
        spacing_scale=spacing_scale,
        radius_scale=radius_scale,
        extra_excludes=extra_excludes,
        top_n_values=top_n_values,
    )


# ============================================================================
# Rendering
# ============================================================================


def _render_human(report: AuditReport) -> str:
    """Markdown-flavoured text summary. Used for stdout and --out files."""
    lines: list[str] = []
    lines.append(f"# Lumo audit — {report.root}\n")
    lines.append(f"- Files scanned: **{report.files_scanned}**")
    lang_str = ", ".join(f"{n} {k}" for k, n in sorted(report.counts_by_language.items()))
    lines.append(f"- By language: {lang_str if lang_str else '—'}")
    lines.append(f"- Files with findings: **{report.files_with_findings}**")
    lines.append(f"- Total findings: **{report.total_findings}**\n")

    if report.counts_by_severity:
        lines.append("## Findings by severity\n")
        for sev in ("critical", "high", "medium", "low", "info"):
            n = report.counts_by_severity.get(sev, 0)
            if n:
                lines.append(f"- **{sev}**: {n}")
        lines.append("")

    if report.counts_by_check:
        lines.append("## Findings by check\n")
        for check, n in sorted(report.counts_by_check.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- `{check}`: {n}")
        lines.append("")

    if report.scale_observations:
        lines.append("## Measured scale\n")
        lines.append(
            "These are the literal numeric values found across the codebase. "
            "Token references (e.g. `MaterialTheme.spacing.md`) are excluded — "
            "we count only hardcoded literals. Compare the top values against "
            "your configured scale to see actual drift.\n"
        )
        for obs in report.scale_observations:
            lines.append(f"### {obs.kind} — {obs.total_literals} literal occurrences\n")
            lines.append("| value | count |")
            lines.append("|---|---|")
            for value, count in obs.values_by_frequency:
                marker = "" if value in obs.on_scale else " ⚠"
                lines.append(f"| {value}{marker} | {count} |")
            lines.append("")
            if obs.off_scale:
                lines.append(
                    f"Off-scale values: `{', '.join(str(v) for v in obs.off_scale)}` "
                    "(⚠ above)."
                )
                lines.append("")

    if report.findings:
        lines.append("## Findings\n")
        for f in report.findings:
            lines.append(
                f"- **[{f.severity.upper()}]** `{f.check}` — "
                f"`{f.file}:{f.line}:{f.column}` — {f.message}"
            )
        lines.append("")

    if report.total_findings == 0 and not report.scale_observations:
        lines.append("✓ No design-system drift detected.\n")

    return "\n".join(lines)


def _render_json(report: AuditReport) -> str:
    """Stable JSON for CI consumption / further tooling."""
    payload = {
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
    return json.dumps(payload, indent=2)


# ============================================================================
# Entry point
# ============================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lumo-audit",
        description="Whole-repository design-system audit for Compose / SwiftUI.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="Scan a repository and report drift.")
    scan.add_argument("--root", required=True, help="Path to the repo root to scan.")
    scan.add_argument(
        "--config",
        default=None,
        help="Path to a lumo.config.json. Reads the `audit` section.",
    )
    scan.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "POSIX-style glob (relative to --root) to exclude. May be "
            "passed multiple times. Stacked on top of the always-skipped "
            "directories (.git, build, node_modules, Pods, etc.)."
        ),
    )
    scan.add_argument(
        "--scale",
        type=_parse_scale,
        default=None,
        help=f"Spacing scale (default: {','.join(str(int(v)) if v.is_integer() else str(v) for v in DEFAULT_SPACING_SCALE_DP)}).",
    )
    scan.add_argument(
        "--radius-scale",
        type=_parse_scale,
        default=None,
        help=f"Radius scale (default: {','.join(str(int(v)) if v.is_integer() else str(v) for v in DEFAULT_RADIUS_SCALE_DP)}).",
    )
    scan.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="How many top frequencies per kind to surface (default 15).",
    )
    scan.add_argument("--json", action="store_true", help="Emit JSON to stdout instead of text.")
    scan.add_argument(
        "--out",
        default=None,
        help="Also write a markdown report to this file path.",
    )

    args = parser.parse_args(argv)

    if args.cmd == "scan":
        config = _build_config(args)
        report = scan_repo(args.root, config=config)

        if args.json:
            print(_render_json(report))
        else:
            print(_render_human(report))

        if args.out:
            Path(args.out).write_text(_render_human(report), encoding="utf-8")

        return 0 if report.total_findings == 0 else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
