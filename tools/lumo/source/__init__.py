"""AST-based source-code checks for Compose / SwiftUI.

Public API:
    check_compose(source, path=...)  -> SourceReport
    check_swiftui(source, path=...)  -> SourceReport     (Phase 2.2)

Detects violations the existing layout-based checks cannot see without
runtime data: hardcoded hex colours, off-scale dp/sp values, undersized
tap targets, asymmetric padding, raw cornerRadius values, and similar
design-system drift.

The output uses the same `Finding` shape as `lumo.theory` / `lumo.parity`
so downstream consumers (CLI, MCP, audit aggregator) can mix all three.
"""

from lumo.source.core import (
    Category,
    SourceFinding,
    SourceReport,
    check_compose,
)

__all__ = [
    "Category",
    "SourceFinding",
    "SourceReport",
    "check_compose",
]
