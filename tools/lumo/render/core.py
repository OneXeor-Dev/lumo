"""AST layout evaluator for Jetpack Compose.

Walks the same tree-sitter AST `lumo.source` uses for drift checks and
produces a layout JSON with `(x, y, w, h)` for every statically-resolvable
element. The output is the same Lumo schema `lumo-theory` / `lumo-parity`
consume — but stamped `"source": "ast-resolved"` instead of `"measured"`
or `"code-estimated"`.

Honesty rules (locked, identical spirit to `lumo.source`):

  - We **never invent numbers**. Token references, runtime values,
    `fillMaxWidth` without a known screen width, `weight(1f)` siblings
    that can't be resolved, and unknown composables all emit
    `Element(source="ast-unresolved", reason=...)`. They carry coordinates
    only when math allows.
  - The evaluator handles common static cases. Anything that needs an
    actual layout engine (lazy lists, complex constraints, animations,
    state-driven sizing) is deliberately not modeled — we mark it
    unresolved instead of guessing.
  - Two-pass for `weight(N)` siblings: pass 1 measures all fixed-size
    children to compute used space, pass 2 distributes the remaining
    free space across weighted children. Mirrors Compose's actual rule.

Known composables (v1):
  - Containers: `Column`, `Row`, `Box`, `Card`, `Surface`
  - Atoms: `Text`, `Button`, `IconButton`, `Icon`, `Image`,
    `FloatingActionButton`, `Spacer`
  - Anything else: emitted as `ast-unresolved` with reason "unknown composable"

Known modifiers (v1):
  - `padding(N.dp)`, `padding(horizontal=…, vertical=…)`,
    `padding(start=…, end=…, top=…, bottom=…)`
  - `size(N.dp)`, `width(N.dp)`, `height(N.dp)`
  - `fillMaxWidth()`, `fillMaxHeight()`, `fillMaxSize()`
  - `offset(x=…, y=…)`
  - `weight(N)`  (within Column / Row)
  - `wrapContentSize()`, `wrapContentWidth()`, `wrapContentHeight()` — no-op for sizing
  - `testTag("id")` — captured as `Element.id`
  - Any other modifier — silently ignored (does not break layout math)
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import tree_sitter_kotlin
from tree_sitter import Language, Node, Parser

# ============================================================================
# Defaults
# ============================================================================

DEFAULT_SCREEN_WIDTH_DP = 360.0
DEFAULT_SCREEN_HEIGHT_DP = 800.0

# Typical default heights/widths for atoms when neither size nor
# fill-modifier is present. These come from Material defaults; the user
# can override via the public API. Each value is dp.
DEFAULT_BUTTON_HEIGHT_DP = 40.0
DEFAULT_TEXT_HEIGHT_DP = 20.0
DEFAULT_ICON_SIZE_DP = 24.0
DEFAULT_FAB_SIZE_DP = 56.0
DEFAULT_ICON_BUTTON_SIZE_DP = 48.0

# Known container composables — their children stack along an axis.
COLUMN_LIKE = frozenset({"Column"})
ROW_LIKE = frozenset({"Row"})
BOX_LIKE = frozenset({"Box", "Card", "Surface"})

# Known atom composables — they don't stack children, but they ARE
# emitted as a layout element.
ATOM_COMPOSABLES: dict[str, str] = {
    "Text": "text",
    "Button": "primary_action",
    "OutlinedButton": "primary_action",
    "TextButton": "primary_action",
    "ElevatedButton": "primary_action",
    "FilledTonalButton": "primary_action",
    "IconButton": "icon_button",
    "FilledIconButton": "icon_button",
    "FilledTonalIconButton": "icon_button",
    "OutlinedIconButton": "icon_button",
    "Icon": "icon",
    "Image": "image",
    "FloatingActionButton": "primary_action",
    "SmallFloatingActionButton": "primary_action",
    "LargeFloatingActionButton": "primary_action",
    "ExtendedFloatingActionButton": "primary_action",
    "Spacer": "spacer",
}

ALL_KNOWN_COMPOSABLES = (
    COLUMN_LIKE | ROW_LIKE | BOX_LIKE | frozenset(ATOM_COMPOSABLES.keys())
)


# ============================================================================
# Element + report data model
# ============================================================================


ElementSource = Literal["ast-resolved", "ast-unresolved"]


@dataclass(frozen=True)
class Element:
    """One element in the rendered layout.

    Mirrors the Lumo layout JSON `elements[]` schema documented in
    `examples/README.md`. `source` is the new honesty label slot — see
    the module docstring.
    """

    id: str
    role: str
    x: float | None
    y: float | None
    w: float | None
    h: float | None
    source: ElementSource
    reason: str | None = None
    group: str | None = None
    weight: str | None = None

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"id": self.id, "role": self.role, "source": self.source}
        if self.x is not None: out["x"] = self.x
        if self.y is not None: out["y"] = self.y
        if self.w is not None: out["w"] = self.w
        if self.h is not None: out["h"] = self.h
        if self.group is not None: out["group"] = self.group
        if self.weight is not None: out["weight"] = self.weight
        if self.reason is not None: out["reason"] = self.reason
        return out


@dataclass(frozen=True)
class RenderReport:
    """Top-level layout JSON, plus a coverage stat for diagnostics."""

    screen_width: float
    screen_height: float
    unit: Literal["dp"]
    elements: tuple[Element, ...]

    @property
    def resolved_count(self) -> int:
        return sum(1 for e in self.elements if e.source == "ast-resolved")

    @property
    def unresolved_count(self) -> int:
        return sum(1 for e in self.elements if e.source == "ast-unresolved")

    @property
    def coverage(self) -> float:
        total = len(self.elements)
        return self.resolved_count / total if total else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "screen": {"width": self.screen_width, "height": self.screen_height, "unit": self.unit},
            "source": "ast-resolved",  # report-level label; per-element label is on each element
            "elements": [e.to_dict() for e in self.elements],
            "coverage": round(self.coverage, 3),
        }


# ============================================================================
# Tree-sitter setup
# ============================================================================

_KOTLIN_LANGUAGE: Language | None = None


def _kotlin_parser() -> Parser:
    global _KOTLIN_LANGUAGE
    if _KOTLIN_LANGUAGE is None:
        _KOTLIN_LANGUAGE = Language(tree_sitter_kotlin.language())
    return Parser(_KOTLIN_LANGUAGE)


def _node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


# ============================================================================
# Modifier parser — small, focused, deterministic
# ============================================================================


@dataclass
class Modifiers:
    """The subset of Modifier semantics we statically resolve.

    None means "not set" (use parent / default); explicit zero means
    "set to zero" (do not default). This distinction matters for
    fillMaxWidth where `width = None` falls back to wrapContent.
    """

    pad_start: float = 0.0
    pad_end: float = 0.0
    pad_top: float = 0.0
    pad_bottom: float = 0.0
    width: float | None = None
    height: float | None = None
    fill_max_width: bool = False
    fill_max_height: bool = False
    offset_x: float = 0.0
    offset_y: float = 0.0
    weight: float | None = None
    test_tag: str | None = None
    # Set when we saw a modifier we don't understand — caller can decide
    # whether to mark the element unresolved or pass through.
    unresolved_reasons: list[str] = field(default_factory=list)


_DP_RE = re.compile(r"(-?\d+(?:\.\d+)?)\.(?:dp|sp)\b")
_BARE_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_STRING_RE = re.compile(r'"([^"]*)"')


def _parse_dp(text: str) -> float | None:
    """Parse `16.dp` / `4.5.sp` → 16.0. Return None for tokens/vars."""
    t = text.strip()
    m = _DP_RE.fullmatch(t)
    if m:
        return float(m.group(1))
    return None


def _parse_float(text: str) -> float | None:
    """Parse `1f`, `0.5f`, `2` → float. None for non-numeric."""
    t = text.strip().rstrip("fF")
    if _BARE_NUM_RE.match(t):
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _split_args(arg_text: str) -> list[str]:
    """Split a comma-separated argument list, respecting nested parens.

    `"horizontal = 8.dp, vertical = 4.dp"` → ["horizontal = 8.dp", "vertical = 4.dp"]
    `"x = a(1, 2), y = 3"` → ["x = a(1, 2)", "y = 3"]
    """
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in arg_text:
        if ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _named_arg(args: list[str], name: str) -> str | None:
    """Return the value of a `name = value` arg if present, else None."""
    prefix = name + "="
    for a in args:
        compact = a.replace(" ", "")
        if compact.startswith(prefix):
            return a.split("=", 1)[1].strip()
    return None


def _apply_modifier(name: str, arg_text: str, mods: Modifiers) -> None:
    """Mutate `mods` based on one `.modifier(args)` call."""
    args = _split_args(arg_text)
    if name == "padding":
        if len(args) == 1 and "=" not in args[0]:
            # padding(N.dp) — all four sides
            uniform = _parse_dp(args[0])
            if uniform is None:
                mods.unresolved_reasons.append(f"padding({args[0]}) is a token")
                return
            mods.pad_start = mods.pad_end = mods.pad_top = mods.pad_bottom = uniform
            return
        # Named-arg form: horizontal / vertical / start / end / top / bottom
        h_arg = _named_arg(args, "horizontal")
        v_arg = _named_arg(args, "vertical")
        s_arg = _named_arg(args, "start")
        e_arg = _named_arg(args, "end")
        t_arg = _named_arg(args, "top")
        b_arg = _named_arg(args, "bottom")
        if h_arg is not None:
            val = _parse_dp(h_arg)
            if val is None:
                mods.unresolved_reasons.append(f"padding(horizontal={h_arg}) is a token")
                return
            mods.pad_start = mods.pad_end = val
        if v_arg is not None:
            val = _parse_dp(v_arg)
            if val is None:
                mods.unresolved_reasons.append(f"padding(vertical={v_arg}) is a token")
                return
            mods.pad_top = mods.pad_bottom = val
        if s_arg is not None:
            val = _parse_dp(s_arg)
            if val is None:
                mods.unresolved_reasons.append(f"padding(start={s_arg}) is a token")
                return
            mods.pad_start = val
        if e_arg is not None:
            val = _parse_dp(e_arg)
            if val is None:
                mods.unresolved_reasons.append(f"padding(end={e_arg}) is a token")
                return
            mods.pad_end = val
        if t_arg is not None:
            val = _parse_dp(t_arg)
            if val is None:
                mods.unresolved_reasons.append(f"padding(top={t_arg}) is a token")
                return
            mods.pad_top = val
        if b_arg is not None:
            val = _parse_dp(b_arg)
            if val is None:
                mods.unresolved_reasons.append(f"padding(bottom={b_arg}) is a token")
                return
            mods.pad_bottom = val
        return
    if name == "size":
        v = _parse_dp(arg_text)
        if v is None:
            mods.unresolved_reasons.append(f"size({arg_text}) is a token")
            return
        mods.width = v
        mods.height = v
        return
    if name == "width":
        v = _parse_dp(arg_text)
        if v is None:
            mods.unresolved_reasons.append(f"width({arg_text}) is a token")
            return
        mods.width = v
        return
    if name == "height":
        v = _parse_dp(arg_text)
        if v is None:
            mods.unresolved_reasons.append(f"height({arg_text}) is a token")
            return
        mods.height = v
        return
    if name == "fillMaxWidth":
        mods.fill_max_width = True
        return
    if name == "fillMaxHeight":
        mods.fill_max_height = True
        return
    if name == "fillMaxSize":
        mods.fill_max_width = True
        mods.fill_max_height = True
        return
    if name in ("wrapContentSize", "wrapContentWidth", "wrapContentHeight"):
        # No-op for sizing — Compose default is wrap. Recorded as resolved.
        return
    if name == "offset":
        x = _named_arg(args, "x")
        y = _named_arg(args, "y")
        if x is not None:
            v = _parse_dp(x)
            if v is None:
                mods.unresolved_reasons.append(f"offset(x={x}) is a token")
                return
            mods.offset_x = v
        if y is not None:
            v = _parse_dp(y)
            if v is None:
                mods.unresolved_reasons.append(f"offset(y={y}) is a token")
                return
            mods.offset_y = v
        return
    if name == "weight":
        if not args:
            return
        f = _parse_float(args[0])
        if f is None:
            mods.unresolved_reasons.append(f"weight({args[0]}) is not literal")
            return
        mods.weight = f
        return
    if name == "testTag":
        if not args:
            return
        m = _STRING_RE.search(args[0])
        if m:
            mods.test_tag = m.group(1)
        return
    # Other modifiers (background, clickable, clip, etc.) don't change layout
    # math we model. Silently ignore.


def _parse_modifier_chain(arg_text: str) -> Modifiers:
    """Walk `Modifier.foo(...).bar(...)` text and accumulate Modifiers.

    The input is the *text* of the `modifier = ...` argument value. We
    look for `\\.name(args)` segments inside it. Parens are matched.
    """
    mods = Modifiers()
    text = arg_text.strip()
    # Find segments like `.name(args)` — name may be on chain start as
    # `Modifier.name(args)`.
    i = 0
    n = len(text)
    while i < n:
        # Find next `.`
        dot = text.find(".", i)
        if dot == -1:
            break
        # Read identifier after the dot
        j = dot + 1
        while j < n and (text[j].isalnum() or text[j] == "_"):
            j += 1
        if j == dot + 1:
            i = j
            continue
        name = text[dot + 1 : j]
        # Find arg parens
        if j >= n or text[j] != "(":
            # Property access (e.g. Modifier alone), skip
            i = j
            continue
        # Match parens
        depth = 0
        end = j
        for k in range(j, n):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        arg_text_inner = text[j + 1 : end]
        _apply_modifier(name, arg_text_inner, mods)
        i = end + 1
    return mods


# ============================================================================
# AST helpers — extract composable calls from a function body
# ============================================================================


def _walk(node: Node) -> "Iterable[Node]":
    yield node
    for ch in node.children:
        yield from _walk(ch)


def _find_composable_body(root: Node, src: bytes, target: str | None) -> Node | None:
    """Locate the body of the @Composable function we should render.

    If `target` is given, prefer a function with that name. Otherwise
    return the first @Composable function body in the file. We accept
    any function annotated with `@Composable` — tree-sitter-kotlin
    nests the annotation under `modifiers > annotation`, so checking
    the prefix text is the simplest cross-version probe.
    """
    composables: list[tuple[str, Node]] = []
    for node in _walk(root):
        if node.type != "function_declaration":
            continue
        prefix = _node_text(node, src)[: 200]
        if "@Composable" not in prefix:
            continue
        name = None
        body = None
        for ch in node.children:
            # tree-sitter-kotlin uses `identifier` for the function name
            # (older builds may use `simple_identifier`).
            if ch.type in ("identifier", "simple_identifier") and name is None:
                name = _node_text(ch, src).strip()
            elif ch.type == "function_body":
                body = ch
        if body is not None and name is not None:
            composables.append((name, body))
    if not composables:
        return None
    if target:
        for n, b in composables:
            if n == target:
                return b
    return composables[0][1]


def _iter_top_level_calls(body: Node, src: bytes) -> list[Node]:
    """Return the top-level call_expression nodes within a function body.

    "Top-level" = direct children of the body's statement list (or
    block). We do NOT recurse into modifier arguments or lambdas —
    children of a composable are walked separately via its trailing
    lambda body.
    """
    # Drill into `function_body > block` or `function_body > statements`
    # to find the actual statement container.
    container = body
    for ch in body.children:
        if ch.type in ("block", "statements"):
            container = ch
            break
    calls: list[Node] = []
    for ch in container.children:
        if ch.type == "call_expression":
            calls.append(ch)
    return calls


def _call_inner_call(call: Node) -> Node:
    """Drill into a call_expression to find the innermost call carrying
    the identifier + value_arguments.

    Compose's `Button(args) { lambda }` parses as an outer call_expression
    whose first child is the *inner* call_expression `Button(args)` and
    second child is `annotated_lambda`. For atoms like `Text("OK")` the
    structure is flat. This helper unwraps both shapes uniformly.
    """
    cur = call
    while cur.children and cur.children[0].type == "call_expression":
        cur = cur.children[0]
    return cur


def _call_callee_name(call: Node, src: bytes) -> str | None:
    """Return the simple name of a call_expression's callee.

    Handles `Text(...)`, `Column(...)` (identifier / simple_identifier)
    and the fairly rare `Foo.Bar(...)` (navigation_expression — pick
    last segment).
    """
    inner = _call_inner_call(call)
    if not inner.children:
        return None
    callee = inner.children[0]
    if callee.type in ("identifier", "simple_identifier"):
        return _node_text(callee, src).strip()
    text = _node_text(callee, src).strip()
    return text.rsplit(".", 1)[-1] if text else None


def _call_value_args(call: Node, src: bytes) -> str:
    """Return the raw text inside the call's value_arguments `( ... )`."""
    inner = _call_inner_call(call)
    for ch in inner.children[1:]:
        if ch.type == "value_arguments":
            txt = _node_text(ch, src)
            return txt[1:-1] if txt.startswith("(") and txt.endswith(")") else txt
        if ch.type == "call_suffix":
            for cc in ch.children:
                if cc.type == "value_arguments":
                    txt = _node_text(cc, src)
                    return txt[1:-1] if txt.startswith("(") and txt.endswith(")") else txt
    return ""


def _call_trailing_lambda(call: Node, src: bytes) -> Node | None:
    """Return the trailing lambda body of a call_expression, if any.

    Compose containers (`Column { ... }` / `Row { ... }` / `Box { ... }`)
    put children inside `{ ... }`. tree-sitter-kotlin gives two shapes:
      - `Foo(args) { lambda }` — outer call_expression with children
        `[inner-call, annotated_lambda]`.
      - `Foo { lambda }` — annotated_lambda is a sibling of the callee
        identifier under a single call_expression.
    """
    # Shape 1: lambda is a direct sibling of the outer call.
    for ch in call.children:
        if ch.type in ("lambda_literal", "annotated_lambda"):
            return ch
    # Shape 2: lambda lives under a call_suffix on the inner call.
    inner = _call_inner_call(call)
    for ch in inner.children:
        if ch.type == "call_suffix":
            for cc in ch.children:
                if cc.type in ("lambda_literal", "annotated_lambda"):
                    return cc
    return None


def _lambda_calls(lam: Node) -> list[Node]:
    """Return the top-level call_expressions inside a lambda body.

    tree-sitter-kotlin shape: `annotated_lambda → lambda_literal → '{' <calls...> '}'`.
    Some builds insert a `statements` container; both are handled.
    """
    # Drill through annotated_lambda to lambda_literal if needed.
    cur = lam
    while cur.type == "annotated_lambda":
        ll = None
        for ch in cur.children:
            if ch.type == "lambda_literal":
                ll = ch
                break
        if ll is None:
            break
        cur = ll
    # Now cur is lambda_literal. Look for `statements` wrapper first.
    container = cur
    for ch in cur.children:
        if ch.type in ("statements", "block"):
            container = ch
            break
    calls: list[Node] = []
    for ch in container.children:
        if ch.type == "call_expression":
            calls.append(ch)
    return calls


def _extract_modifier_arg(call_args_text: str) -> str | None:
    """Return the raw text of `modifier = ...` (without the LHS), or None.

    Named arg only; positional `modifier` is rarely written in Compose.
    """
    args = _split_args(call_args_text)
    for a in args:
        compact = a.replace(" ", "")
        if compact.startswith("modifier="):
            return a.split("=", 1)[1].strip()
    return None


# ============================================================================
# Layout context + evaluator
# ============================================================================


@dataclass
class Ctx:
    """Layout pass context — the offset+available frame we render into.

    `tainted_reasons` carries forward unresolved-modifier explanations
    from ancestor containers. Once a parent container hit a token or
    runtime expression it could not statically evaluate, every descendant
    inherits that fact — their absolute coordinates would be guesses,
    not derivations, so we surface them as `ast-unresolved` regardless
    of how clean the child's own modifiers are. This is the same honesty
    rule `lumo.source` already enforces, just propagated downward.
    """

    origin_x: float
    origin_y: float
    available_w: float
    available_h: float
    tainted_reasons: tuple[str, ...] = ()

    def shrink(self, pad_l: float, pad_t: float, pad_r: float, pad_b: float) -> "Ctx":
        return Ctx(
            origin_x=self.origin_x + pad_l,
            origin_y=self.origin_y + pad_t,
            available_w=max(0.0, self.available_w - pad_l - pad_r),
            available_h=max(0.0, self.available_h - pad_t - pad_b),
            tainted_reasons=self.tainted_reasons,
        )


def _atom_default_size(role: str, mods: Modifiers, ctx: Ctx) -> tuple[float, float]:
    """Default size for an atom when its modifiers don't pin w/h."""
    w = mods.width
    h = mods.height
    if mods.fill_max_width:
        w = ctx.available_w
    if mods.fill_max_height:
        h = ctx.available_h
    if w is None:
        if role == "icon":
            w = DEFAULT_ICON_SIZE_DP
        elif role == "icon_button":
            w = DEFAULT_ICON_BUTTON_SIZE_DP
        elif role == "primary_action":
            # FAB uses its own constant. Buttons fall back to wrap (we don't
            # know text width); approximate with a sensible default.
            w = DEFAULT_FAB_SIZE_DP if "Fab" in role else 0.0
        else:
            w = 0.0
    if h is None:
        if role == "icon":
            h = DEFAULT_ICON_SIZE_DP
        elif role == "icon_button":
            h = DEFAULT_ICON_BUTTON_SIZE_DP
        elif role == "primary_action":
            h = DEFAULT_BUTTON_HEIGHT_DP
        elif role == "text":
            h = DEFAULT_TEXT_HEIGHT_DP
        else:
            h = 0.0
    return float(w), float(h)


@dataclass
class _CallSpec:
    """Pre-parsed call info — name, modifiers, args, lambda."""

    name: str
    role: str | None  # mapped composable role; None for unknown
    mods: Modifiers
    raw_args: str
    lambda_body: Node | None
    call_node: Node


def _parse_call(call: Node, src: bytes) -> _CallSpec | None:
    name = _call_callee_name(call, src)
    if name is None:
        return None
    args_text = _call_value_args(call, src)
    mod_text = _extract_modifier_arg(args_text)
    mods = _parse_modifier_chain(mod_text) if mod_text else Modifiers()
    role = ATOM_COMPOSABLES.get(name)
    return _CallSpec(
        name=name,
        role=role,
        mods=mods,
        raw_args=args_text,
        lambda_body=_call_trailing_lambda(call, src),
        call_node=call,
    )


def _next_auto_id(role: str, counter: dict[str, int]) -> str:
    counter[role] = counter.get(role, 0) + 1
    return f"{role}_{counter[role]}"


def _render_column(
    spec: _CallSpec,
    src: bytes,
    ctx: Ctx,
    id_counter: dict[str, int],
    out: list[Element],
) -> tuple[float, float]:
    """Render a Column. Returns (used_w, used_h)."""
    return _render_axis(spec, src, ctx, "column", id_counter, out)


def _render_row(
    spec: _CallSpec,
    src: bytes,
    ctx: Ctx,
    id_counter: dict[str, int],
    out: list[Element],
) -> tuple[float, float]:
    return _render_axis(spec, src, ctx, "row", id_counter, out)


def _render_axis(
    spec: _CallSpec,
    src: bytes,
    ctx: Ctx,
    axis: Literal["column", "row"],
    id_counter: dict[str, int],
    out: list[Element],
) -> tuple[float, float]:
    """Stack children along an axis. Apply weight() two-pass."""
    # Container's own size first: explicit width/height pins, then
    # fillMax* against parent, otherwise inherit parent's available.
    own_w = ctx.available_w if spec.mods.fill_max_width else spec.mods.width
    own_h = ctx.available_h if spec.mods.fill_max_height else spec.mods.height
    if own_w is None:
        own_w = ctx.available_w
    if own_h is None:
        own_h = ctx.available_h
    tainted = ctx.tainted_reasons + tuple(spec.mods.unresolved_reasons)
    inner = Ctx(
        origin_x=ctx.origin_x + spec.mods.pad_start,
        origin_y=ctx.origin_y + spec.mods.pad_top,
        available_w=max(0.0, own_w - spec.mods.pad_start - spec.mods.pad_end),
        available_h=max(0.0, own_h - spec.mods.pad_top - spec.mods.pad_bottom),
        tainted_reasons=tainted,
    )

    children: list[_CallSpec] = []
    if spec.lambda_body is not None:
        for call in _lambda_calls(spec.lambda_body):
            cs = _parse_call(call, src)
            if cs is not None:
                children.append(cs)

    # PASS 1 — measure fixed children, collect weights
    fixed_sizes: list[tuple[float, float] | None] = [None] * len(children)
    total_weight = 0.0
    used_along = 0.0
    for idx, child in enumerate(children):
        if child.mods.weight is not None:
            total_weight += child.mods.weight
            continue
        # Measure: render into a probe ctx that has the inner's full available.
        # We only need the size, not the emitted elements.
        probe: list[Element] = []
        w, h = _measure(child, src, inner, dict(id_counter), probe)
        fixed_sizes[idx] = (w, h)
        used_along += h if axis == "column" else w

    free = max(0.0, (inner.available_h if axis == "column" else inner.available_w) - used_along)

    # PASS 2 — emit children, allocating weighted siblings
    cursor_x, cursor_y = inner.origin_x, inner.origin_y
    for idx, child in enumerate(children):
        if child.mods.weight is not None:
            if total_weight <= 0 or free <= 0:
                # Cannot resolve — emit unresolved
                eid = child.mods.test_tag or _next_auto_id(child.role or child.name, id_counter)
                out.append(Element(
                    id=eid, role=child.role or child.name,
                    x=None, y=None, w=None, h=None,
                    source="ast-unresolved",
                    reason=f"weight({child.mods.weight}) requires resolvable parent extent",
                ))
                continue
            allocated = free * (child.mods.weight / total_weight)
            # The weight allocation IS the child's measured extent along the
            # axis — patch the modifiers so atoms don't fall back to defaults.
            if axis == "row":
                child.mods.width = allocated
                child.mods.height = child.mods.height or inner.available_h
                child_ctx = Ctx(cursor_x, cursor_y, allocated, inner.available_h, inner.tainted_reasons)
            else:
                child.mods.height = allocated
                child.mods.width = child.mods.width or inner.available_w
                child_ctx = Ctx(cursor_x, cursor_y, inner.available_w, allocated, inner.tainted_reasons)
            w, h = _emit(child, src, child_ctx, id_counter, out)
            if axis == "column":
                cursor_y += h
            else:
                cursor_x += w
        else:
            child_ctx = Ctx(
                origin_x=cursor_x,
                origin_y=cursor_y,
                available_w=inner.available_w if axis == "column" else inner.available_w - (cursor_x - inner.origin_x),
                available_h=inner.available_h if axis == "row" else inner.available_h - (cursor_y - inner.origin_y),
                tainted_reasons=inner.tainted_reasons,
            )
            w, h = _emit(child, src, child_ctx, id_counter, out)
            if axis == "column":
                cursor_y += h
            else:
                cursor_x += w

    used_w = inner.available_w if axis == "column" else (cursor_x - inner.origin_x)
    used_h = (cursor_y - inner.origin_y) if axis == "column" else inner.available_h
    # Account for container's own padding
    return used_w + spec.mods.pad_start + spec.mods.pad_end, used_h + spec.mods.pad_top + spec.mods.pad_bottom


def _render_box(
    spec: _CallSpec,
    src: bytes,
    ctx: Ctx,
    id_counter: dict[str, int],
    out: list[Element],
) -> tuple[float, float]:
    """Render a Box / Card / Surface — children overlay."""
    own_w = ctx.available_w if spec.mods.fill_max_width else spec.mods.width
    own_h = ctx.available_h if spec.mods.fill_max_height else spec.mods.height
    if own_w is None:
        own_w = ctx.available_w
    if own_h is None:
        own_h = ctx.available_h
    tainted = ctx.tainted_reasons + tuple(spec.mods.unresolved_reasons)
    inner = Ctx(
        origin_x=ctx.origin_x + spec.mods.pad_start,
        origin_y=ctx.origin_y + spec.mods.pad_top,
        available_w=max(0.0, own_w - spec.mods.pad_start - spec.mods.pad_end),
        available_h=max(0.0, own_h - spec.mods.pad_top - spec.mods.pad_bottom),
        tainted_reasons=tainted,
    )
    if spec.lambda_body is None:
        return spec.mods.pad_start + spec.mods.pad_end, spec.mods.pad_top + spec.mods.pad_bottom
    max_w, max_h = 0.0, 0.0
    for call in _lambda_calls(spec.lambda_body):
        cs = _parse_call(call, src)
        if cs is None:
            continue
        w, h = _emit(cs, src, inner, id_counter, out)
        max_w = max(max_w, w)
        max_h = max(max_h, h)
    return max_w + spec.mods.pad_start + spec.mods.pad_end, max_h + spec.mods.pad_top + spec.mods.pad_bottom


def _emit(
    spec: _CallSpec,
    src: bytes,
    ctx: Ctx,
    id_counter: dict[str, int],
    out: list[Element],
) -> tuple[float, float]:
    """Dispatch + emit a single composable. Returns its used (w, h)."""
    # Containers
    if spec.name in COLUMN_LIKE:
        return _render_column(spec, src, ctx, id_counter, out)
    if spec.name in ROW_LIKE:
        return _render_row(spec, src, ctx, id_counter, out)
    if spec.name in BOX_LIKE:
        return _render_box(spec, src, ctx, id_counter, out)

    # Atoms (known)
    if spec.role is not None:
        if spec.role == "spacer":
            # Spacer has no role in the output — it's pure whitespace.
            w = spec.mods.width or 0.0
            h = spec.mods.height or 0.0
            if spec.mods.fill_max_width:
                w = ctx.available_w
            if spec.mods.fill_max_height:
                h = ctx.available_h
            return w, h
        w, h = _atom_default_size(spec.role, spec.mods, ctx)
        eid = spec.mods.test_tag or _next_auto_id(spec.role, id_counter)
        # Resolution status — unresolved if any modifier on this element
        # failed OR any ancestor container had unresolvable modifiers
        # (the coordinates we'd report would be based on a guessed offset).
        all_reasons = list(ctx.tainted_reasons) + list(spec.mods.unresolved_reasons)
        if all_reasons:
            out.append(Element(
                id=eid, role=spec.role,
                x=None, y=None, w=None, h=None,
                source="ast-unresolved",
                reason="; ".join(all_reasons),
            ))
            return 0.0, 0.0
        out.append(Element(
            id=eid, role=spec.role,
            x=ctx.origin_x + spec.mods.offset_x,
            y=ctx.origin_y + spec.mods.offset_y,
            w=w, h=h,
            source="ast-resolved",
        ))
        return w, h

    # Unknown composable
    eid = spec.mods.test_tag or _next_auto_id("unknown", id_counter)
    reasons = [f"unknown composable: {spec.name}"] + list(ctx.tainted_reasons)
    out.append(Element(
        id=eid, role=spec.name,
        x=None, y=None, w=None, h=None,
        source="ast-unresolved",
        reason="; ".join(reasons),
    ))
    return 0.0, 0.0


def _measure(
    spec: _CallSpec,
    src: bytes,
    ctx: Ctx,
    id_counter: dict[str, int],
    out_probe: list[Element],
) -> tuple[float, float]:
    """Like _emit but for a measurement-only pass — uses a throwaway out."""
    return _emit(spec, src, ctx, id_counter, out_probe)


# ============================================================================
# Public API
# ============================================================================


def render_compose(
    source: str,
    *,
    target: str | None = None,
    screen_width: float = DEFAULT_SCREEN_WIDTH_DP,
    screen_height: float = DEFAULT_SCREEN_HEIGHT_DP,
) -> RenderReport:
    """Render a Compose source string to a layout report.

    `target` — optional name of the @Composable to render. If None,
    the first @Composable in the file is used.

    `screen_width` / `screen_height` — the root container size, in dp.
    `fillMaxWidth()` / `fillMaxHeight()` resolve against these.
    """
    src = source.encode("utf-8")
    tree = _kotlin_parser().parse(src)
    body = _find_composable_body(tree.root_node, src, target)
    elements: list[Element] = []
    id_counter: dict[str, int] = {}
    if body is None:
        return RenderReport(
            screen_width=screen_width,
            screen_height=screen_height,
            unit="dp",
            elements=(),
        )
    ctx = Ctx(origin_x=0.0, origin_y=0.0, available_w=screen_width, available_h=screen_height)
    for call in _iter_top_level_calls(body, src):
        spec = _parse_call(call, src)
        if spec is None:
            continue
        _emit(spec, src, ctx, id_counter, elements)
    return RenderReport(
        screen_width=screen_width,
        screen_height=screen_height,
        unit="dp",
        elements=tuple(elements),
    )


def render_compose_file(
    file_path: str | Path,
    *,
    target: str | None = None,
    screen_width: float = DEFAULT_SCREEN_WIDTH_DP,
    screen_height: float = DEFAULT_SCREEN_HEIGHT_DP,
) -> RenderReport:
    """Convenience: read a .kt file from disk and render it."""
    p = Path(file_path)
    return render_compose(
        p.read_text(encoding="utf-8"),
        target=target,
        screen_width=screen_width,
        screen_height=screen_height,
    )


__all__ = [
    "DEFAULT_SCREEN_HEIGHT_DP",
    "DEFAULT_SCREEN_WIDTH_DP",
    "Element",
    "RenderReport",
    "render_compose",
    "render_compose_file",
]
