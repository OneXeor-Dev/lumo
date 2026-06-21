"""Orchestrator: fetch spec -> cap -> LLM -> validate -> SpecReport.

This is the pipeline from docs/design/spec-check/02-algorithm.md, minus the
arg-parsing and emission steps (those live in cli.py / output.py). It is the
single seam that tests drive with a fake `Caller`.
"""

from __future__ import annotations

from typing import Any

from lumo.spec.layout import elements_count, layout_source
from lumo.spec.llm import Caller, run_llm
from lumo.spec.models import SEVERITIES, Finding, SpecDocument, SpecReport
from lumo.spec.validators import (
    coerce_findings,
    enforce_length_cap,
    validate_evidence,
)

_SEVERITY_RANK = {sev: i for i, sev in enumerate(SEVERITIES)}  # high=0 ... low=2


def run_check(
    *,
    spec: SpecDocument,
    layout: dict[str, Any],
    caller: Caller,
    model: str,
    severity_floor: str | None = None,
    char_cap: int | None = None,
) -> SpecReport:
    """Run a full spec-vs-layout check and return a SpecReport.

    Raises SpecTooLongError if the spec is over cap, LLMError on an
    unrecoverable model failure. Both surface as exit code 2 in the CLI.
    """
    from lumo.spec.validators import SPEC_CHAR_CAP

    enforce_length_cap(spec.markdown, char_cap or SPEC_CHAR_CAP)

    result = run_llm(
        caller=caller,
        spec_markdown=spec.markdown,
        layout=layout,
        model=model,
    )

    findings, dropped_schema = coerce_findings(result.findings)
    findings, dropped_fab = validate_evidence(findings, spec.markdown)
    findings = _apply_severity_floor(findings, severity_floor)
    findings = _sort_findings(findings)

    return SpecReport(
        model=model,
        spec=spec,
        layout_source=layout_source(layout),
        layout_elements_count=elements_count(layout),
        findings=tuple(findings),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        dropped_fabricated=dropped_fab,
    )


def _apply_severity_floor(
    findings: list[Finding], floor: str | None
) -> list[Finding]:
    if not floor:
        return findings
    max_rank = _SEVERITY_RANK[floor]
    return [f for f in findings if _SEVERITY_RANK[f.severity] <= max_rank]


def _sort_findings(findings: list[Finding]) -> list[Finding]:
    """Highest severity first, stable within a severity (preserves LLM order)."""
    return sorted(findings, key=lambda f: _SEVERITY_RANK[f.severity])
