"""Data model for lumo-spec.

The finding envelope mirrors the rest of Lumo (`lumo-theory`, `lumo-source`)
with two spec-specific fields — `confidence` and `evidence` — per
docs/design/spec-check/03-outputs.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# Locked enums. The structured-output schema (llm.py) enforces these so the
# model cannot invent ids, severities, or confidence levels.
FindingId = Literal[
    "missing_required_element",
    "element_count_mismatch",
    "behavioural_constraint_violation",
    "copy_mismatch",
    "extraneous_element",
    "ambiguous_requirement",
]
Severity = Literal["high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]

FINDING_IDS: tuple[str, ...] = (
    "missing_required_element",
    "element_count_mismatch",
    "behavioural_constraint_violation",
    "copy_mismatch",
    "extraneous_element",
    "ambiguous_requirement",
)
SEVERITIES: tuple[str, ...] = ("high", "medium", "low")
CONFIDENCES: tuple[str, ...] = ("high", "medium", "low")


@dataclass(frozen=True)
class SpecDocument:
    """A fetched, flattened specification.

    Every source plugin returns one of these. `markdown` carries the
    flattening guarantees from docs/design/spec-check/01-inputs.md.
    """

    source_type: str  # "markdown" | "confluence" | "jira"
    source_id: str
    title: str
    markdown: str
    fetched_at: datetime
    raw_url: str | None = None

    @property
    def character_count(self) -> int:
        return len(self.markdown)


@dataclass(frozen=True)
class Finding:
    """A single spec-vs-layout discrepancy."""

    id: FindingId
    severity: Severity
    confidence: Confidence
    message: str
    evidence: str
    recommendation: str
    element: str | None = None


@dataclass(frozen=True)
class SpecReport:
    """The full result of a spec check — the JSON envelope."""

    model: str
    spec: SpecDocument
    layout_source: str
    layout_elements_count: int
    findings: tuple[Finding, ...]
    input_tokens: int | None = None
    output_tokens: int | None = None
    dropped_fabricated: int = 0  # findings rejected by the evidence validator

    @property
    def counts_by_severity(self) -> dict[str, int]:
        out = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            out[f.severity] += 1
        return out

    @property
    def counts_by_confidence(self) -> dict[str, int]:
        out = {c: 0 for c in CONFIDENCES}
        for f in self.findings:
            out[f.confidence] += 1
        return out
