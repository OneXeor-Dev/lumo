"""AST-based source checks for Jetpack Compose `.kt` files.

We use `tree-sitter-kotlin` to parse the file and walk Modifier chains,
Color() constructors, Shape declarations, and similar design-system
surfaces. Findings carry:
  - a category (a11y / consistency / token / theory)
  - a file location (path, line, column)
  - a severity
  - a recommendation

Honesty rules (locked):
  - We never invent numbers. If we cannot statically evaluate a value
    (e.g. it references `MaterialTheme.spacing.md` or a `LocalDimensions`
    composition local) we treat it as a **valid token use** and skip
    the finding. The point is to catch *hardcoded* drift, not flag
    every theme reference.
  - All findings inherit `source: "code-estimated"` — even though the
    parser is deterministic, we cannot resolve runtime values, so the
    confidence label stays honest about the input shape.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import tree_sitter_kotlin
from tree_sitter import Language, Node, Parser

Category = Literal["a11y", "consistency", "token", "theory"]
Severity = Literal["critical", "high", "medium", "low", "info"]

# ============================================================================
# Defaults — overridable via lumo.config.json in higher-level commands.
# ============================================================================

# Material 3 + Apple HIG-flavoured default spacing scale.
# Values outside this scale flag a "consistency" finding.
DEFAULT_SPACING_SCALE_DP: tuple[float, ...] = (0.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0, 32.0, 40.0, 48.0, 56.0, 64.0)
DEFAULT_RADIUS_SCALE_DP: tuple[float, ...] = (0.0, 4.0, 8.0, 12.0, 16.0, 24.0, 28.0, 32.0)

MIN_TAP_TARGET_DP = 48.0  # Material minimum

# Modifier names that take a single-dimension value (the .dp at call sites).
SIZE_MODIFIERS = {"size", "width", "height", "minWidth", "minHeight"}
PADDING_MODIFIERS = {"padding"}
SHAPE_MODIFIERS = {"clip"}

# ============================================================================
# Finding model
# ============================================================================


@dataclass(frozen=True)
class SourceFinding:
    check: str
    category: Category
    severity: Severity
    file: str
    line: int
    column: int
    snippet: str
    message: str
    recommendation: str
    metric: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceReport:
    findings: tuple[SourceFinding, ...]
    file: str
    language: Literal["kotlin", "swift"]

    @property
    def counts_by_severity(self) -> dict[Severity, int]:
        result: dict[Severity, int] = {}
        for f in self.findings:
            result[f.severity] = result.get(f.severity, 0) + 1
        return result

    @property
    def counts_by_category(self) -> dict[Category, int]:
        result: dict[Category, int] = {}
        for f in self.findings:
            result[f.category] = result.get(f.category, 0) + 1
        return result


# ============================================================================
# Tree-sitter setup (cached per process)
# ============================================================================

_KOTLIN_LANGUAGE: Language | None = None


def _kotlin_parser() -> Parser:
    global _KOTLIN_LANGUAGE
    if _KOTLIN_LANGUAGE is None:
        _KOTLIN_LANGUAGE = Language(tree_sitter_kotlin.language())
    return Parser(_KOTLIN_LANGUAGE)


# ============================================================================
# AST helpers
# ============================================================================


def _node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Node) -> Iterator[Node]:
    """Depth-first walk over the tree-sitter tree."""
    yield node
    for child in node.children:
        yield from _walk(child)


def _parse_dp_literal(text: str) -> float | None:
    """Parse expressions like `16.dp`, `4.5.dp`, `0.dp` → float.

    Returns None if the text doesn't look like a literal dp value
    (e.g. it's `MaterialTheme.spacing.md.dp` or `someVar.dp`).
    """
    text = text.strip()
    if not text.endswith(".dp") and not text.endswith(".sp"):
        return None
    candidate = text[:-3]  # strip .dp / .sp
    try:
        return float(candidate)
    except ValueError:
        return None


def _parse_hex_color(text: str) -> str | None:
    """Parse `Color(0xFFRRGGBB)` or `Color(0xFFFFFFFF)` → '#RRGGBB'.

    Returns None when the call references a token (`MaterialTheme.colorScheme.primary`),
    a named constant (`Color.Red`), or anything else non-literal.
    """
    text = text.strip()
    if not (text.startswith("Color(") and text.endswith(")")):
        return None
    inner = text[len("Color(") : -1].strip()
    if not inner.lower().startswith("0x"):
        return None
    hex_part = inner[2:].strip().rstrip("L").upper()
    if len(hex_part) == 8:
        # 0xAARRGGBB — alpha first
        rgb = hex_part[2:]
    elif len(hex_part) == 6:
        rgb = hex_part
    else:
        return None
    if not all(c in "0123456789ABCDEF" for c in rgb):
        return None
    return "#" + rgb


# ============================================================================
# Modifier-chain walker
# ============================================================================


def _iter_modifier_calls(root: Node, src: bytes) -> Iterator[tuple[str, str, Node]]:
    """Yield (call_name, arg_text, node) for every `Modifier.<call>(args)`
    or chained `.<call>(args)` we can see.

    Tree-sitter for Kotlin gives us `call_expression` nodes whose first
    child is a `navigation_expression`. We walk every call_expression in
    the tree and check if its receiver chain starts with `Modifier`.
    """
    for node in _walk(root):
        if node.type != "call_expression":
            continue
        # The callee is the first child (the navigation_expression).
        if not node.children:
            continue
        callee = node.children[0]
        callee_text = _node_text(callee, src)
        # Match `Modifier.foo` or `Modifier.foo.bar` or `.foo` continuation.
        if ".dp" in callee_text and not callee_text.startswith("Modifier"):
            # Skip e.g. `16.dp` calls — those are unit-conversion expressions
            # and not modifier calls.
            continue
        if "Modifier" not in callee_text and not callee_text.startswith("."):
            continue
        # Extract the last method name.
        last_segment = callee_text.rsplit(".", 1)[-1]
        # The arguments are after the callee; the rest of the call_expression.
        # We just take the text between `(` and matching `)`.
        full_text = _node_text(node, src)
        paren_idx = full_text.find("(")
        if paren_idx == -1:
            continue
        # Find matching closing paren — simple depth counter is enough.
        depth = 0
        end_idx = -1
        for i, ch in enumerate(full_text[paren_idx:], start=paren_idx):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        if end_idx == -1:
            continue
        arg_text = full_text[paren_idx + 1 : end_idx]
        yield last_segment, arg_text, node


# ============================================================================
# Checks
# ============================================================================


def _location(node: Node, path: str) -> tuple[str, int, int]:
    return (path, node.start_point[0] + 1, node.start_point[1] + 1)


def _check_modifier_calls(
    root: Node,
    src: bytes,
    path: str,
    spacing_scale: tuple[float, ...],
    radius_scale: tuple[float, ...],
) -> list[SourceFinding]:
    findings: list[SourceFinding] = []

    for name, arg_text, node in _iter_modifier_calls(root, src):
        file_, line, col = _location(node, path)

        # --- size / width / height / minWidth / minHeight ---------------
        if name in SIZE_MODIFIERS:
            value = _parse_dp_literal(arg_text)
            if value is None:
                # Token reference or computed — fine.
                continue
            # Hardcoded numeric size — flag if below tap-target minimum AND
            # the parent looks like an interactive surface. We don't have
            # parent context yet (Phase 2 enhancement), so for now we only
            # flag when value > 0 and < MIN_TAP_TARGET_DP and the modifier
            # is `size` (most common for icon buttons).
            if name == "size" and 0 < value < MIN_TAP_TARGET_DP:
                findings.append(
                    SourceFinding(
                        check="undersized_tap_target",
                        category="a11y",
                        severity="high",
                        file=file_, line=line, column=col,
                        snippet=_node_text(node, src),
                        message=(
                            f"Modifier.size({value}.dp) is below the Material "
                            f"minimum tap target ({MIN_TAP_TARGET_DP}dp)."
                        ),
                        recommendation=(
                            "Grow the element to at least 48dp, or extend the "
                            "hit area with Modifier.minimumInteractiveComponentSize() "
                            "while keeping the visual size."
                        ),
                        metric={"value_dp": value, "minimum_dp": MIN_TAP_TARGET_DP},
                    )
                )

        # --- padding (single literal value) ------------------------------
        if name in PADDING_MODIFIERS:
            # Only flag the simple `padding(N.dp)` shape. Named args like
            # `padding(horizontal = 8.dp)` are intentionally skipped in v1.
            stripped = arg_text.strip()
            if "=" in stripped or "," in stripped:
                continue
            value = _parse_dp_literal(stripped)
            if value is None:
                continue  # token reference — fine
            if value not in spacing_scale:
                findings.append(
                    SourceFinding(
                        check="off_scale_spacing",
                        category="consistency",
                        severity="medium",
                        file=file_, line=line, column=col,
                        snippet=_node_text(node, src),
                        message=(
                            f"Modifier.padding({value}.dp) is not on the spacing "
                            f"scale (allowed: {list(spacing_scale)})."
                        ),
                        recommendation=(
                            "Round to the nearest scale value, or move this value "
                            "into a spacing token if it is a deliberate exception."
                        ),
                        metric={"value_dp": value, "scale": list(spacing_scale)},
                    )
                )

    return findings


def _check_color_literals(root: Node, src: bytes, path: str) -> list[SourceFinding]:
    findings: list[SourceFinding] = []
    for node in _walk(root):
        if node.type != "call_expression":
            continue
        if not node.children:
            continue
        callee_text = _node_text(node.children[0], src).strip()
        if callee_text != "Color":
            continue
        full = _node_text(node, src)
        hex_value = _parse_hex_color(full)
        if hex_value is None:
            continue
        file_, line, col = _location(node, path)
        findings.append(
            SourceFinding(
                check="hardcoded_color",
                category="token",
                severity="medium",
                file=file_, line=line, column=col,
                snippet=full,
                message=(
                    f"Hardcoded Color({hex_value}) bypasses the design-system "
                    "colour tokens — refactor will be invisible to this call site."
                ),
                recommendation=(
                    "Replace with MaterialTheme.colorScheme.<role> "
                    "(primary / surface / onBackground / etc.) so a theme "
                    "update reaches every consumer at once."
                ),
                metric={"hex": hex_value},
            )
        )
    return findings


def _check_corner_radius(
    root: Node, src: bytes, path: str, radius_scale: tuple[float, ...]
) -> list[SourceFinding]:
    findings: list[SourceFinding] = []
    for node in _walk(root):
        if node.type != "call_expression":
            continue
        if not node.children:
            continue
        callee_text = _node_text(node.children[0], src).strip()
        if callee_text != "RoundedCornerShape":
            continue
        full = _node_text(node, src)
        paren_idx = full.find("(")
        end_idx = full.rfind(")")
        if paren_idx == -1 or end_idx <= paren_idx:
            continue
        inner = full[paren_idx + 1 : end_idx].strip()
        if "," in inner or "=" in inner:
            continue  # per-corner — skip for v1
        value = _parse_dp_literal(inner)
        if value is None:
            continue
        if value in radius_scale:
            continue
        file_, line, col = _location(node, path)
        findings.append(
            SourceFinding(
                check="off_scale_radius",
                category="consistency",
                severity="low",
                file=file_, line=line, column=col,
                snippet=full,
                message=(
                    f"RoundedCornerShape({value}.dp) is not on the radius scale "
                    f"(allowed: {list(radius_scale)})."
                ),
                recommendation=(
                    "Use a value from the radius scale, or define a named "
                    "Shape in MaterialTheme.shapes if this radius is deliberate."
                ),
                metric={"value_dp": value, "scale": list(radius_scale)},
            )
        )
    return findings


# ============================================================================
# Entry point
# ============================================================================


def check_compose(
    source: str,
    path: str = "<source>",
    spacing_scale: tuple[float, ...] = DEFAULT_SPACING_SCALE_DP,
    radius_scale: tuple[float, ...] = DEFAULT_RADIUS_SCALE_DP,
) -> SourceReport:
    """Run AST checks on a Compose .kt source string. Returns a SourceReport.

    `path` is only used for finding locations; the actual content comes
    from `source`. Pass a filesystem path when scanning from disk.
    """
    src = source.encode("utf-8")
    parser = _kotlin_parser()
    tree = parser.parse(src)
    root = tree.root_node

    findings: list[SourceFinding] = []
    findings.extend(_check_modifier_calls(root, src, path, spacing_scale, radius_scale))
    findings.extend(_check_color_literals(root, src, path))
    findings.extend(_check_corner_radius(root, src, path, radius_scale))

    severity_order: dict[Severity, int] = {
        "critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4,
    }
    findings.sort(key=lambda f: (severity_order[f.severity], f.file, f.line))

    return SourceReport(findings=tuple(findings), file=path, language="kotlin")


def check_compose_file(
    file_path: str | Path,
    spacing_scale: tuple[float, ...] = DEFAULT_SPACING_SCALE_DP,
    radius_scale: tuple[float, ...] = DEFAULT_RADIUS_SCALE_DP,
) -> SourceReport:
    """Convenience: read a .kt file from disk and check it."""
    p = Path(file_path)
    return check_compose(
        p.read_text(encoding="utf-8"),
        path=str(p),
        spacing_scale=spacing_scale,
        radius_scale=radius_scale,
    )
