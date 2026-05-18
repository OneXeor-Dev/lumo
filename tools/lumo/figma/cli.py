"""CLI for `lumo-figma` — compare Figma design tokens against code.

Usage:
    # Diff a Figma file against a `lumo-audit` JSON report on disk.
    lumo-figma diff --file-key abc123 --audit audit.json

    # Or against a live repo (runs `lumo-audit` inline).
    lumo-figma diff --file-key abc123 --root path/to/repo

    # Pick a specific variable-collection mode (default: each collection's
    # default mode).
    lumo-figma diff --file-key abc123 --root . --mode Dark

    # Lower the missing-token threshold for noisier projects.
    lumo-figma diff --file-key abc123 --audit a.json --missing-threshold 5

    # Machine-readable.
    lumo-figma diff --file-key abc123 --audit a.json --json

Auth:
    Set FIGMA_TOKEN in the environment. We never read the token from a
    CLI flag — flags end up in shell history. Generate a personal access
    token at https://www.figma.com/developers and export it before
    running:

        export FIGMA_TOKEN=figd_xxx…
        lumo-figma diff --file-key … --audit …

Exit codes:
    0 — Figma and code are in lock-step (no missing-from-figma values).
    1 — Drift detected (at least one missing-from-figma).
    2 — Argument / config / API error.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lumo.audit.core import scan_repo
from lumo.figma.core import (
    FigmaApiError,
    FigmaDiffReport,
    FigmaTokens,
    diff_against_audit,
    fetch_tokens,
    parse_figma_url,
)


# ============================================================================
# Audit input — file or live scan
# ============================================================================


def _load_audit_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Return a `lumo-audit` JSON payload — either from disk or live."""
    if args.audit and args.root:
        raise SystemExit("Pass --audit OR --root, not both.")
    if not args.audit and not args.root:
        raise SystemExit("Pass --audit <path.json> or --root <repo path>.")

    if args.audit:
        path = Path(args.audit)
        try:
            return _to_dict(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            raise SystemExit(f"audit file not found: {path}")
        except json.JSONDecodeError as e:
            raise SystemExit(f"audit file is not valid JSON: {path}: {e}")

    # Live scan via the in-process scan_repo. We import locally to keep
    # the CLI module's `import time` cheap when the user passed --audit.
    report = scan_repo(args.root)
    return {
        "files_scanned": report.files_scanned,
        "scale_observations": [
            {
                "kind": obs.kind,
                "total_literals": obs.total_literals,
                "values_by_frequency": [
                    {"value": v, "count": c} for v, c in obs.values_by_frequency
                ],
            }
            for obs in report.scale_observations
        ],
        "findings": [asdict(f) for f in report.findings],
    }


def _to_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit("audit JSON must be an object")
    return value


# ============================================================================
# Rendering
# ============================================================================


def _render_human(figma: FigmaTokens, report: FigmaDiffReport) -> str:
    lines: list[str] = []
    lines.append(f"# Lumo ↔ Figma — file {report.file_key} (mode: {report.mode_label})\n")

    figma_total = (
        len(figma.colors) + len(figma.floats) + len(figma.strings) + len(figma.booleans)
    )
    lines.append(f"- Figma tokens fetched: **{figma_total}** "
                 f"({len(figma.colors)} COLOR, {len(figma.floats)} FLOAT, "
                 f"{len(figma.strings)} STRING, {len(figma.booleans)} BOOLEAN)")
    lines.append(f"- Matched in code: **{report.summary_counts.get('matched', 0)}**")
    lines.append(f"- Unused in code: **{report.summary_counts.get('unused_in_code', 0)}**")
    lines.append(
        f"- Used in code but missing from Figma: "
        f"**{report.summary_counts.get('missing_from_figma', 0)}**\n"
    )

    if report.matched:
        lines.append("## Matched tokens\n")
        lines.append("| Token | Type | Value | Code kind | Code uses |")
        lines.append("|---|---|---|---|---|")
        for match in report.matched:
            lines.append(
                f"| `{match.token.name}` | {match.token.type} | "
                f"`{match.token.value_canonical}` | {match.code_kind} | "
                f"{match.code_occurrences} |"
            )
        lines.append("")

    if report.unused_in_code:
        lines.append("## Unused in code\n")
        lines.append(
            "Tokens declared in Figma whose value is never literal-used in code. "
            "Note: matches are by VALUE — a token may still be used via theme "
            "indirection (`MaterialTheme.colorScheme.*`, `LocalDimensions.*`) "
            "without showing up here. Treat this list as candidates for review, "
            "not as a hit-list for deletion.\n"
        )
        lines.append("| Token | Type | Value | Collection |")
        lines.append("|---|---|---|---|")
        for unused in report.unused_in_code:
            lines.append(
                f"| `{unused.token.name}` | {unused.token.type} | "
                f"`{unused.token.value_canonical}` | {unused.token.collection} |"
            )
        lines.append("")

    if report.missing_from_figma:
        lines.append("## Missing from Figma\n")
        lines.append(
            "Hardcoded values used heavily in code with no matching Figma token. "
            "Strong candidates for promotion to the design system.\n"
        )
        lines.append("| Value | Kind | Uses |")
        lines.append("|---|---|---|")
        for missing in report.missing_from_figma:
            lines.append(
                f"| `{missing.value}` | {missing.code_kind} | "
                f"{missing.code_occurrences} |"
            )
        lines.append("")

    if not (report.matched or report.unused_in_code or report.missing_from_figma):
        lines.append("✓ Figma file has no COLOR / FLOAT variables, or no "
                     "comparable values in the audit payload.\n")

    return "\n".join(lines)


def _render_json(figma: FigmaTokens, report: FigmaDiffReport) -> str:
    payload = {
        "file_key": report.file_key,
        "mode_label": report.mode_label,
        "summary_counts": dict(report.summary_counts),
        "matched": [
            {
                "token": _token_to_dict(m.token),
                "code_kind": m.code_kind,
                "code_occurrences": m.code_occurrences,
            }
            for m in report.matched
        ],
        "unused_in_code": [
            {"token": _token_to_dict(u.token)} for u in report.unused_in_code
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
    return json.dumps(payload, indent=2)


def _token_to_dict(token: Any) -> dict[str, Any]:
    return {
        "id": token.id,
        "name": token.name,
        "type": token.type,
        "collection": token.collection,
        "mode_name": token.mode_name,
        "value": token.value_canonical,
        "is_alias_resolved": token.is_alias_resolved,
    }


# ============================================================================
# Entry point
# ============================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lumo-figma",
        description="Compare Figma design tokens against the code's measured scale.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    diff = sub.add_parser("diff", help="Diff Figma tokens against a code audit.")
    diff.add_argument(
        "--file-key",
        default=None,
        help="Figma file key (the `abc123` part of a Figma URL).",
    )
    diff.add_argument(
        "--url",
        default=None,
        help="Or pass a Figma URL — we'll extract the file key for you.",
    )
    diff.add_argument(
        "--audit",
        default=None,
        help="Path to a lumo-audit --json output to compare against.",
    )
    diff.add_argument(
        "--root",
        default=None,
        help="Or scan this repo root with lumo-audit inline.",
    )
    diff.add_argument(
        "--mode",
        default=None,
        help="Variable-collection mode name (default: each collection's default).",
    )
    diff.add_argument(
        "--missing-threshold",
        type=int,
        default=3,
        help="Min code occurrences before a value is flagged 'missing from Figma'.",
    )
    diff.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    diff.add_argument(
        "--out",
        default=None,
        help="Also write a markdown report to this path.",
    )

    args = parser.parse_args(argv)

    if args.cmd == "diff":
        file_key = args.file_key
        if not file_key and args.url:
            parsed = parse_figma_url(args.url)
            file_key = parsed.file_key
        if not file_key:
            print(
                "Pass --file-key <key> or --url <figma-url>.",
                file=sys.stderr,
            )
            return 2

        audit_payload = _load_audit_payload(args)

        try:
            figma = fetch_tokens(file_key, mode=args.mode)
        except FigmaApiError as e:
            print(f"figma: {e}", file=sys.stderr)
            return 2

        report = diff_against_audit(
            figma,
            audit_payload,
            missing_threshold=args.missing_threshold,
        )

        if args.json:
            print(_render_json(figma, report))
        else:
            print(_render_human(figma, report))

        if args.out:
            Path(args.out).write_text(_render_human(figma, report), encoding="utf-8")

        return 1 if report.summary_counts.get("missing_from_figma", 0) > 0 else 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
