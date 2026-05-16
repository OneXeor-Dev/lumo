"""Cognitive-science checks for mobile UI layouts.

Public API:
    check_layout(layout) -> ReportSummary

Checks implemented:
    - fitts_difficulty   — relative comparison of interactive targets
    - hick_overload      — flags equal-weight choices that exceed comfort
    - gestalt_proximity  — intra-group spacing must be smaller than inter-group
    - reach              — primary actions in reachable zones, not top corners

Honest design notes:
    - Output is findings + recommendations, not absolute Fitts/Hick times.
      Absolute MT/RT depend on device-specific constants (a, b) that have
      ±40% variance across studies. Relative ratios are device-independent.
    - Every finding carries a confidence based on the input source:
      "measured" > "code-estimated" > "description-estimated".
    - Nielsen heuristics are NOT in this tool — they aren't reliably
      numeric. They live as inline rules in SKILL.md instead.
"""

from lumo.theory.core import (
    Confidence,
    Element,
    Finding,
    Layout,
    ReportSummary,
    Screen,
    Severity,
    check_layout,
)

__all__ = [
    "Confidence",
    "Element",
    "Finding",
    "Layout",
    "ReportSummary",
    "Screen",
    "Severity",
    "check_layout",
]
