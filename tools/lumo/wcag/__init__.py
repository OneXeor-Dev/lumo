"""WCAG contrast validator and OKLCH auto-correct.

Public API:
    relative_luminance(hex_color)  -> float in [0, 1]
    contrast_ratio(fg, bg)         -> float in [1, 21]
    check_pair(fg, bg, level, size) -> CheckResult
    auto_correct(fg, bg, level, size) -> CorrectionResult
"""

from lumo.wcag.core import (
    CheckResult,
    CorrectionResult,
    auto_correct,
    check_pair,
    contrast_ratio,
    relative_luminance,
)

__all__ = [
    "CheckResult",
    "CorrectionResult",
    "auto_correct",
    "check_pair",
    "contrast_ratio",
    "relative_luminance",
]
