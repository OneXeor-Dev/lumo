"""AST-based source-code checks for Compose / SwiftUI.

Public API:
    check_compose(source, path=...)  -> SourceReport     (Compose / Kotlin)
    check_swiftui(source, path=...)  -> SourceReport     (SwiftUI / Swift)

Detects violations the existing layout-based checks cannot see without
runtime data: hardcoded hex colours, off-scale dp/sp values, undersized
tap targets, asymmetric padding, raw cornerRadius values, and similar
design-system drift.

The output uses the same `Finding` shape as `lumo.theory` / `lumo.parity`
so downstream consumers (CLI, MCP, audit aggregator) can mix all three.
"""

from lumo.source.core import (
    Category,
    LiteralValue,
    SourceFinding,
    SourceReport,
    check_compose,
    check_swiftui,
    iter_compose_literals,
    iter_swiftui_literals,
)

__all__ = [
    "Category",
    "LiteralValue",
    "SourceFinding",
    "SourceReport",
    "check_compose",
    "check_swiftui",
    "iter_compose_literals",
    "iter_swiftui_literals",
]
