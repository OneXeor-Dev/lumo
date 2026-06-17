"""CLI for lumo-spec — semantic spec-vs-layout check.

Usage:
    lumo-spec check --layout screen.json --spec ./prd.md
    lumo-spec check --layout screen.json --source markdown --spec ./prd.md
    cat screen.json | lumo-spec check --layout - --spec ./prd.md

Confluence and Jira sources (--source confluence --page-id …,
--source jira --issue-key …, --url …) are accepted by the parser and land in
Phases 2 and 3; until then they exit 2 with a clear "not in this build" message.

Exit codes: 0 = no findings · 1 = findings reported · 2 = tool error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from lumo.spec.check import run_check
from lumo.spec.layout import LayoutError, load_layout
from lumo.spec.llm import DEFAULT_MODEL, AnthropicCaller, Caller, LLMError
from lumo.spec.output import print_human, print_json, to_json_dict
from lumo.spec.sources import SourceError, get_source
from lumo.spec.validators import SpecTooLongError

_CONFLUENCE_URL = re.compile(r"atlassian\.net/wiki/spaces/[^/]+/pages/(\d+)")
_JIRA_URL = re.compile(r"atlassian\.net/browse/([A-Z][A-Z0-9]+-\d+)")


def _infer_source_from_url(url: str) -> tuple[str, str]:
    """Return (source, identifier) inferred from an Atlassian URL, or exit 2."""
    if (m := _CONFLUENCE_URL.search(url)) is not None:
        return "confluence", m.group(1)
    if (m := _JIRA_URL.search(url)) is not None:
        return "jira", m.group(1)
    raise SourceError(f"could not infer source from url: {url}")


def _resolve_source(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve (source_name, identifier) from the CLI flags.

    Mirrors the matrix in docs/design/spec-check/01-inputs.md.
    """
    if args.url:
        source, identifier = _infer_source_from_url(args.url)
        if args.source and args.source != source:
            raise SourceError(
                f"--url implies source '{source}' but --source={args.source} was given"
            )
        return source, identifier

    source = args.source
    if args.spec and not source:
        source = "markdown"

    if source == "markdown":
        if not args.spec:
            raise SourceError("--source markdown requires --spec PATH")
        return "markdown", args.spec
    if source == "confluence":
        if not args.page_id:
            raise SourceError("--source confluence requires --page-id ID")
        return "confluence", args.page_id
    if source == "jira":
        if not args.issue_key:
            raise SourceError("--source jira requires --issue-key KEY")
        return "jira", args.issue_key

    raise SourceError(
        "specify a spec source: --spec PATH, or --source {markdown|confluence|jira} "
        "with its identifier, or --url <atlassian-url>"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lumo-spec",
        description="Semantic check: does the layout satisfy the product spec? "
        "(LLM-backed — every finding is 'llm-derived' with evidence + confidence.)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Check a layout against a spec.")
    check.add_argument("--layout", required=True, help="Path to layout JSON, or '-' for stdin.")

    check.add_argument("--source", choices=["markdown", "confluence", "jira"], default=None)
    check.add_argument("--spec", help="Path to a Markdown spec file.")
    check.add_argument("--page-id", dest="page_id", help="Confluence page id.")
    check.add_argument("--issue-key", dest="issue_key", help="Jira issue key.")
    check.add_argument("--url", help="Atlassian URL; source inferred when --source omitted.")

    check.add_argument("--json", action="store_true", help="Emit JSON.")
    check.add_argument("--out", help="Write findings JSON to a file.")
    check.add_argument(
        "--severity-floor",
        choices=["high", "medium", "low"],
        default=None,
        help="Drop findings below this severity.",
    )

    check.add_argument("--model", default=None, help=f"LLM model id (default: {DEFAULT_MODEL}).")
    check.add_argument("--base-url", dest="base_url", default=None, help="Anthropic-compatible base URL.")
    return parser


def main(argv: list[str] | None = None, *, caller: Caller | None = None) -> int:
    """Entry point. `caller` is injectable so tests bypass the live API."""
    args = _build_parser().parse_args(argv)
    if args.cmd != "check":  # pragma: no cover - argparse guards this
        return 2

    try:
        source_name, identifier = _resolve_source(args)
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Sources not yet shipped in this phase.
    if source_name in ("confluence", "jira"):
        print(
            f"error: source '{source_name}' is not in this build yet "
            "(ships in a later phase). Use --spec with a Markdown file.",
            file=sys.stderr,
        )
        return 2

    try:
        spec = get_source(source_name)().fetch(identifier)
    except (SourceError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        layout = load_layout(args.layout)
    except LayoutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    model = args.model or DEFAULT_MODEL
    if caller is None:
        try:
            caller = AnthropicCaller(base_url=args.base_url)
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    try:
        report = run_check(
            spec=spec,
            layout=layout,
            caller=caller,
            model=model,
            severity_floor=args.severity_floor,
        )
    except SpecTooLongError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.out:
        import json as _json

        Path(args.out).write_text(
            _json.dumps(to_json_dict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if args.json:
        print_json(report)
    else:
        print_human(report)

    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())
