"""Whole-repository audit — walks .kt / .swift files, runs lumo.source on
each, and aggregates findings + a frequency table of literal spacing /
radius values across the codebase.

Public API:
    scan_repo(root, config=...)  -> AuditReport

The aggregate view is what `lumo-source` (per-file) cannot answer:

  - Which check fires most often across the project? (drift hotspots)
  - Which numeric values appear most often? (de-facto spacing scale —
    compare against the configured one to see actual drift, not just
    individual rule violations)

`lumo-audit` does NOT propose changes. It surfaces measured data and
lets a human decide. The honesty rule from `lumo.source` carries over:
token references are never counted, only hardcoded literals.
"""

from lumo.audit.core import (
    AuditConfig,
    AuditReport,
    ScaleObservation,
    scan_repo,
)

__all__ = [
    "AuditConfig",
    "AuditReport",
    "ScaleObservation",
    "scan_repo",
]
