"""AST layout evaluator for Jetpack Compose.

Public API:
    render_compose(source, ...) -> RenderReport
    render_compose_file(path, ...) -> RenderReport

Output is the same Lumo layout JSON schema `lumo-theory` / `lumo-parity`
consume, with per-element `source` set to `ast-resolved` or
`ast-unresolved` (with a `reason`). See the module docstring for the
honesty rules.
"""

from lumo.render.core import (
    DEFAULT_SCREEN_HEIGHT_DP,
    DEFAULT_SCREEN_WIDTH_DP,
    Element,
    RenderReport,
    render_compose,
    render_compose_file,
)

__all__ = [
    "DEFAULT_SCREEN_HEIGHT_DP",
    "DEFAULT_SCREEN_WIDTH_DP",
    "Element",
    "RenderReport",
    "render_compose",
    "render_compose_file",
]
