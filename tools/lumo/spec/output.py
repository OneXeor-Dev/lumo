"""Text + JSON emitters for lumo-spec.

Text format mirrors lumo-theory so humans, CI logs, and the annotated-PNG
generator treat all Lumo output uniformly. JSON is the envelope from
docs/design/spec-check/03-outputs.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from lumo.spec.models import SpecReport


def to_json_dict(report: SpecReport) -> dict[str, Any]:
    return {
        "tool": "lumo-spec",
        "source": "llm-derived",
        "model": report.model,
        "spec": {
            "source_type": report.spec.source_type,
            "source_id": report.spec.source_id,
            "fetched_at": report.spec.fetched_at.isoformat().replace("+00:00", "Z"),
            "character_count": report.spec.character_count,
        },
        "layout": {
            "source": report.layout_source,
            "elements_count": report.layout_elements_count,
        },
        "findings": [asdict(f) for f in report.findings],
        "summary": {
            "total": len(report.findings),
            "by_severity": report.counts_by_severity,
            "by_confidence": report.counts_by_confidence,
        },
        "usage": {
            "input_tokens": report.input_tokens,
            "output_tokens": report.output_tokens,
        },
    }


def print_json(report: SpecReport) -> None:
    print(json.dumps(to_json_dict(report), indent=2, ensure_ascii=False))


def print_human(report: SpecReport) -> None:
    chars = f"{report.spec.character_count:,}"
    header = (
        f"SPEC vs LAYOUT — {report.spec.source_id}\n"
        f"Model: {report.model}  ·  Spec chars: {chars}  ·  "
        f"Layout elements: {report.layout_elements_count}"
    )
    print(header)
    print()

    if not report.findings:
        print("OK  no spec-vs-layout findings.")
        return

    counts = report.counts_by_severity
    severity_summary = ", ".join(f"{counts[s]} {s}" for s in ("high", "medium", "low"))
    print(f"FOUND  {len(report.findings)} findings ({severity_summary})")
    print()

    for i, f in enumerate(report.findings, 1):
        where = f" · {f.element}" if f.element else ""
        print(f"  {i}. [{f.severity.upper():8}] {f.id}{where}")
        print(f"     {f.message}")
        print(f'     Evidence: "{f.evidence}"')
        print(f"     → {f.recommendation}")
        print(f"     Confidence: {f.confidence}")
        print()
