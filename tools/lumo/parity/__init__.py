"""Cross-platform parity diff for Android (Compose / XML) vs iOS (SwiftUI / UIKit).

Public API:
    diff(android, ios, config=None) -> ParityReport

The diff compares two layout JSONs (same schema as theory_check) and, when
provided, validates both against a shared design-system config.

Honest design notes:
    - dp and pt are both density-independent. A 16dp / 16pt comparison is
      legitimate (NOT 16dp / 48pt — that's a known junior misconception).
    - Some numeric discrepancies are *expected* per platform standards
      (44pt touch target vs 48dp, 49pt Tab Bar vs 80dp bottom nav,
      17pt iOS body text vs 16sp Material). These live in the whitelist
      and are reported as `info`, not `mismatch`.
    - Confidence propagates from the lower of the two input sources.
"""

from lumo.parity.core import (
    DesignSystemConfig,
    ParityFinding,
    ParityReport,
    diff,
)

__all__ = [
    "DesignSystemConfig",
    "ParityFinding",
    "ParityReport",
    "diff",
]
