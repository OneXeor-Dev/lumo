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
import tree_sitter_swift
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

MIN_TAP_TARGET_DP = 48.0  # Material minimum (Compose)
MIN_TAP_TARGET_PT = 44.0  # Apple HIG minimum (SwiftUI)

# Modifier names that take a single-dimension value (the .dp at call sites).
SIZE_MODIFIERS = {"size", "width", "height", "minWidth", "minHeight"}
PADDING_MODIFIERS = {"padding"}
SHAPE_MODIFIERS = {"clip"}

# SwiftUI uses bare pt — no .dp suffix. Modifier names map similarly.
SWIFTUI_SIZE_MODIFIERS = {"frame"}
SWIFTUI_PADDING_MODIFIERS = {"padding"}
SWIFTUI_RADIUS_MODIFIERS = {"cornerRadius"}

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
_SWIFT_LANGUAGE: Language | None = None


def _kotlin_parser() -> Parser:
    global _KOTLIN_LANGUAGE
    if _KOTLIN_LANGUAGE is None:
        _KOTLIN_LANGUAGE = Language(tree_sitter_kotlin.language())
    return Parser(_KOTLIN_LANGUAGE)


def _swift_parser() -> Parser:
    global _SWIFT_LANGUAGE
    if _SWIFT_LANGUAGE is None:
        _SWIFT_LANGUAGE = Language(tree_sitter_swift.language())
    return Parser(_SWIFT_LANGUAGE)


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


_SEVERITY_ORDER: dict[Severity, int] = {
    "critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4,
}


def _sort_findings(findings: list[SourceFinding]) -> list[SourceFinding]:
    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.file, f.line))
    return findings


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

    return SourceReport(findings=tuple(_sort_findings(findings)), file=path, language="kotlin")


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


# ============================================================================
# SwiftUI checks
# ============================================================================
#
# SwiftUI surfaces differ from Compose:
#   - No .dp / .sp suffix — numbers are bare pt (`.padding(16)`).
#   - Touch-target minimum is 44pt (Apple HIG), not 48dp.
#   - Colors come in several shapes: `Color(red:green:blue:)`,
#     `Color(.sRGB, red:..., green:..., blue:...)`, `Color(hex: "...")`
#     (custom extension), or `Color.red` (named constant).
#   - Per-corner radii are not a single-modifier shape — modern SwiftUI
#     uses `.clipShape(RoundedRectangle(cornerRadius:))`; we only check
#     the simple `.cornerRadius(N)` shape in v1 (and `RoundedRectangle`
#     literal radii where statically resolvable).
#
# Honesty rule (same as Compose): if a value is a token / variable /
# computed expression we cannot resolve statically, we skip it. We only
# flag hardcoded literals.


def _swift_pt_value(node: Node, src: bytes) -> float | None:
    """Return the float value when `node` is an integer or real literal.

    Tree-sitter-swift uses `integer_literal` and `real_literal` for bare
    numbers. Anything else (an identifier, a member access, a unary
    expression) means we cannot statically resolve the value — return
    None and skip per the honesty rule.
    """
    if node.type not in ("integer_literal", "real_literal"):
        return None
    try:
        return float(_node_text(node, src))
    except ValueError:
        return None


def _swift_value_argument_value(arg: Node, src: bytes) -> Node | None:
    """For a `value_argument` node, return the AST node holding the value
    (the part after `label:`). If the argument is a bare expression with
    no label, return the first non-trivia child."""
    if arg.type != "value_argument":
        return None
    # With a label, the children are: value_argument_label, ':', <value>.
    # Without a label, the children are just [<value>].
    has_label = any(c.type == "value_argument_label" for c in arg.children)
    if not has_label:
        for c in arg.children:
            if c.is_named:
                return c
        return None
    found_colon = False
    for c in arg.children:
        if c.type == ":":
            found_colon = True
            continue
        if found_colon and c.is_named:
            return c
    return None


def _swift_value_argument_label(arg: Node, src: bytes) -> str | None:
    """Return the textual label of a value_argument, or None if unlabelled."""
    for c in arg.children:
        if c.type == "value_argument_label":
            return _node_text(c, src).strip()
    return None


def _iter_swiftui_modifier_calls(
    root: Node, src: bytes
) -> Iterator[tuple[str, Node, Node]]:
    """Yield (modifier_name, value_arguments_node, call_expression_node)
    for every `.<modifier>(...)` call in the tree.

    SwiftUI's chained modifiers parse as: a `call_expression` whose first
    child is a `navigation_expression` whose last `navigation_suffix`
    holds the modifier name. The matching `call_suffix.value_arguments`
    is the second child of the outer call_expression.
    """
    for node in _walk(root):
        if node.type != "call_expression":
            continue
        if len(node.children) < 2:
            continue
        callee = node.children[0]
        if callee.type != "navigation_expression":
            continue
        # The last navigation_suffix names the modifier.
        nav_suffix = None
        for c in callee.children:
            if c.type == "navigation_suffix":
                nav_suffix = c
        if nav_suffix is None:
            continue
        name_node = None
        for c in nav_suffix.children:
            if c.type == "simple_identifier":
                name_node = c
                break
        if name_node is None:
            continue
        name = _node_text(name_node, src).strip()
        # Find the value_arguments under the call_suffix.
        value_args = None
        for c in node.children[1:]:
            if c.type == "call_suffix":
                for cc in c.children:
                    if cc.type == "value_arguments":
                        value_args = cc
                        break
                break
        if value_args is None:
            continue
        yield name, value_args, node


def _check_swiftui_modifiers(
    root: Node,
    src: bytes,
    path: str,
    spacing_scale: tuple[float, ...],
    radius_scale: tuple[float, ...],
) -> list[SourceFinding]:
    findings: list[SourceFinding] = []
    for name, value_args, node in _iter_swiftui_modifier_calls(root, src):
        file_, line, col = _location(node, path)
        args = [c for c in value_args.children if c.type == "value_argument"]

        # --- .frame(width:height:) ----------------------------------------
        if name in SWIFTUI_SIZE_MODIFIERS:
            labelled: dict[str, float] = {}
            unresolved = False
            for a in args:
                label = _swift_value_argument_label(a, src)
                if label is None:
                    # `.frame(alignment: .center)` or similar — skip.
                    continue
                value_node = _swift_value_argument_value(a, src)
                if value_node is None:
                    continue
                v = _swift_pt_value(value_node, src)
                if v is None:
                    unresolved = True
                    continue
                labelled[label] = v
            if unresolved:
                # At least one dimension is a token / variable — skip per
                # honesty rule rather than partially flagging.
                continue
            # If width AND height are both literal AND both < HIG min, flag.
            dims = [labelled[k] for k in ("width", "height") if k in labelled]
            if dims and all(0 < d < MIN_TAP_TARGET_PT for d in dims) and len(dims) >= 2:
                smaller = min(dims)
                findings.append(
                    SourceFinding(
                        check="undersized_tap_target",
                        category="a11y",
                        severity="high",
                        file=file_, line=line, column=col,
                        snippet=_node_text(node, src),
                        message=(
                            f".frame(width: {labelled.get('width')}, "
                            f"height: {labelled.get('height')}) is below the "
                            f"Apple HIG minimum tap target ({MIN_TAP_TARGET_PT}pt)."
                        ),
                        recommendation=(
                            "Grow the element to at least 44pt × 44pt, or extend the "
                            "hit area with .contentShape(Rectangle()) and a larger "
                            "containing frame while keeping the visual size."
                        ),
                        metric={
                            "value_pt": smaller,
                            "minimum_pt": MIN_TAP_TARGET_PT,
                        },
                    )
                )

        # --- .padding(...) ------------------------------------------------
        if name in SWIFTUI_PADDING_MODIFIERS:
            # Three shapes we handle:
            #   .padding()                  → default 16pt, skip (no literal)
            #   .padding(16)                → one unlabelled numeric arg
            #   .padding(.horizontal, 16)   → an edge then a numeric arg
            # We only check the trailing numeric literal. Anything else is
            # skipped per the honesty rule.
            numeric_arg: float | None = None
            saw_unresolved = False
            for a in args:
                # We accept either an unlabelled bare numeric, or a labelled
                # arg whose value is numeric (Swift devs rarely label
                # padding amount, but be lenient).
                value_node = _swift_value_argument_value(a, src)
                if value_node is None:
                    continue
                if value_node.type == "prefix_expression":
                    # `.horizontal`, `.top`, etc — skip
                    continue
                v = _swift_pt_value(value_node, src)
                if v is None:
                    saw_unresolved = True
                    continue
                numeric_arg = v
            if numeric_arg is None:
                continue
            if saw_unresolved:
                # Some part is a token — skip to stay honest.
                continue
            if numeric_arg not in spacing_scale:
                findings.append(
                    SourceFinding(
                        check="off_scale_spacing",
                        category="consistency",
                        severity="medium",
                        file=file_, line=line, column=col,
                        snippet=_node_text(node, src),
                        message=(
                            f".padding({numeric_arg}) is not on the spacing "
                            f"scale (allowed: {list(spacing_scale)})."
                        ),
                        recommendation=(
                            "Round to the nearest scale value, or move this value "
                            "into a spacing constant if it is a deliberate exception."
                        ),
                        metric={"value_pt": numeric_arg, "scale": list(spacing_scale)},
                    )
                )

        # --- .cornerRadius(N) --------------------------------------------
        if name in SWIFTUI_RADIUS_MODIFIERS:
            if len(args) != 1:
                continue
            value_node = _swift_value_argument_value(args[0], src)
            if value_node is None:
                continue
            v = _swift_pt_value(value_node, src)
            if v is None:
                continue  # token / variable — skip
            if v in radius_scale:
                continue
            findings.append(
                SourceFinding(
                    check="off_scale_radius",
                    category="consistency",
                    severity="low",
                    file=file_, line=line, column=col,
                    snippet=_node_text(node, src),
                    message=(
                        f".cornerRadius({v}) is not on the radius scale "
                        f"(allowed: {list(radius_scale)})."
                    ),
                    recommendation=(
                        "Use a value from the radius scale, or define a named "
                        "constant if this radius is deliberate."
                    ),
                    metric={"value_pt": v, "scale": list(radius_scale)},
                )
            )
    return findings


def _check_swiftui_color_literals(root: Node, src: bytes, path: str) -> list[SourceFinding]:
    """Flag `Color(red:green:blue:)` and `Color(.sRGB, red:..., green:..., blue:...)`
    literals where every channel is a numeric literal.

    Skipped (honesty rule):
      - `Color.red` / `Color.primary` — named constants, may be a theme alias
      - `Color("brandPrimary")` — asset-catalog lookup, treated as a token
      - `Color(red: brand.r, green: ...)` — any non-literal channel
      - `Color(hex: "...")` — custom extension; we'd need to know which
        extension to interpret it. Documented limitation.
    """
    findings: list[SourceFinding] = []
    for node in _walk(root):
        if node.type != "call_expression":
            continue
        if not node.children:
            continue
        callee = node.children[0]
        # Top-level `Color(...)` — callee is `simple_identifier` "Color".
        if callee.type != "simple_identifier":
            continue
        if _node_text(callee, src).strip() != "Color":
            continue
        # Find value_arguments.
        value_args = None
        for c in node.children[1:]:
            if c.type == "call_suffix":
                for cc in c.children:
                    if cc.type == "value_arguments":
                        value_args = cc
                        break
                break
        if value_args is None:
            continue
        args = [c for c in value_args.children if c.type == "value_argument"]

        # Collect labelled numeric channels.
        channels: dict[str, float] = {}
        had_non_numeric_channel = False
        for a in args:
            label = _swift_value_argument_label(a, src)
            if label is None:
                # First positional arg might be `.sRGB`, `.displayP3`, etc.
                value_node = _swift_value_argument_value(a, src)
                if value_node is not None and value_node.type == "prefix_expression":
                    continue
                # Or it might be a string ("brandPrimary") for asset lookup.
                if value_node is not None and "string_literal" in value_node.type:
                    had_non_numeric_channel = True
                continue
            if label not in ("red", "green", "blue", "opacity", "alpha"):
                # Unknown labels (hex, white) — skip honestly.
                had_non_numeric_channel = True
                continue
            value_node = _swift_value_argument_value(a, src)
            if value_node is None:
                had_non_numeric_channel = True
                continue
            v = _swift_pt_value(value_node, src)
            if v is None:
                had_non_numeric_channel = True
                continue
            channels[label] = v

        # Need r/g/b all numeric to flag.
        if had_non_numeric_channel:
            continue
        if not {"red", "green", "blue"} <= channels.keys():
            continue
        # Build an #RRGGBB string for the message.
        def _to_byte(v: float) -> int:
            return max(0, min(255, round(v * 255 if 0 <= v <= 1 else v)))
        hex_val = "#{:02X}{:02X}{:02X}".format(
            _to_byte(channels["red"]),
            _to_byte(channels["green"]),
            _to_byte(channels["blue"]),
        )
        file_, line, col = _location(node, path)
        findings.append(
            SourceFinding(
                check="hardcoded_color",
                category="token",
                severity="medium",
                file=file_, line=line, column=col,
                snippet=_node_text(node, src),
                message=(
                    f"Hardcoded Color({hex_val}) bypasses the design-system "
                    "colour tokens — refactor will be invisible to this call site."
                ),
                recommendation=(
                    "Replace with an asset-catalog Color or a named constant "
                    "(Color(\"brandPrimary\"), Color.theme.accent) so a theme "
                    "update reaches every consumer at once."
                ),
                metric={"hex": hex_val, "channels": channels},
            )
        )
    return findings


def check_swiftui(
    source: str,
    path: str = "<source>",
    spacing_scale: tuple[float, ...] = DEFAULT_SPACING_SCALE_DP,
    radius_scale: tuple[float, ...] = DEFAULT_RADIUS_SCALE_DP,
) -> SourceReport:
    """Run AST checks on a SwiftUI .swift source string. Returns a SourceReport.

    Mirrors `check_compose` but for SwiftUI. The same scales apply: dp and
    pt are both density-independent and equal in physical size on screen,
    so a `16` budget makes sense on both platforms. We re-use the same
    spacing / radius defaults intentionally.
    """
    src = source.encode("utf-8")
    parser = _swift_parser()
    tree = parser.parse(src)
    root = tree.root_node

    findings: list[SourceFinding] = []
    findings.extend(_check_swiftui_modifiers(root, src, path, spacing_scale, radius_scale))
    findings.extend(_check_swiftui_color_literals(root, src, path))

    return SourceReport(findings=tuple(_sort_findings(findings)), file=path, language="swift")


def check_swiftui_file(
    file_path: str | Path,
    spacing_scale: tuple[float, ...] = DEFAULT_SPACING_SCALE_DP,
    radius_scale: tuple[float, ...] = DEFAULT_RADIUS_SCALE_DP,
) -> SourceReport:
    """Convenience: read a .swift file from disk and check it."""
    p = Path(file_path)
    return check_swiftui(
        p.read_text(encoding="utf-8"),
        path=str(p),
        spacing_scale=spacing_scale,
        radius_scale=radius_scale,
    )
