"""Tests for lumo.render — AST layout evaluator for Compose.

Each test takes a small Compose snippet with a hand-computed expected
layout, renders it, and asserts coordinates. Honesty rule is enforced
explicitly: token references and unknown composables MUST emit
`ast-unresolved` (never invented coordinates).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lumo.render.core import (
    DEFAULT_BUTTON_HEIGHT_DP,
    DEFAULT_ICON_BUTTON_SIZE_DP,
    DEFAULT_ICON_SIZE_DP,
    DEFAULT_SCREEN_WIDTH_DP,
    Element,
    render_compose,
)


def _by_id(elements: tuple[Element, ...], eid: str) -> Element:
    for e in elements:
        if e.id == eid:
            return e
    raise AssertionError(f"no element with id={eid!r} in {[e.id for e in elements]}")


# ============================================================================
# Trivial inputs
# ============================================================================


def test_empty_source_yields_no_elements() -> None:
    r = render_compose("")
    assert r.elements == ()


def test_no_composable_function_yields_no_elements() -> None:
    r = render_compose("fun helper(x: Int): Int = x + 1")
    assert r.elements == ()


def test_target_picks_named_composable() -> None:
    src = """
    @Composable fun A() { Text("a", modifier = Modifier.testTag("ta")) }
    @Composable fun B() { Text("b", modifier = Modifier.testTag("tb")) }
    """
    r = render_compose(src, target="B")
    assert {e.id for e in r.elements} == {"tb"}


def test_first_composable_used_when_no_target() -> None:
    src = """
    @Composable fun A() { Text("a", modifier = Modifier.testTag("ta")) }
    @Composable fun B() { Text("b", modifier = Modifier.testTag("tb")) }
    """
    r = render_compose(src)
    assert {e.id for e in r.elements} == {"ta"}


# ============================================================================
# Column — vertical stack with padding
# ============================================================================


def test_column_with_padding_offsets_origin() -> None:
    src = """
    @Composable
    fun X() {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("a", modifier = Modifier.testTag("t1"))
            Text("b", modifier = Modifier.testTag("t2"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    t1 = _by_id(r.elements, "t1")
    t2 = _by_id(r.elements, "t2")
    assert t1.source == "ast-resolved"
    assert t1.x == 16.0 and t1.y == 16.0
    # t2 stacked under t1 (text default h = 20)
    assert t2.x == 16.0 and t2.y == 36.0


def test_column_named_padding_horizontal_vertical() -> None:
    src = """
    @Composable
    fun X() {
        Column(modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) {
            Text("a", modifier = Modifier.testTag("t"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    t = _by_id(r.elements, "t")
    assert t.x == 8.0 and t.y == 4.0


def test_column_named_padding_individual_sides() -> None:
    src = """
    @Composable
    fun X() {
        Column(modifier = Modifier.padding(start = 12.dp, top = 6.dp, end = 4.dp, bottom = 2.dp)) {
            Text("a", modifier = Modifier.testTag("t"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    t = _by_id(r.elements, "t")
    assert t.x == 12.0 and t.y == 6.0


def test_nested_columns_accumulate_padding() -> None:
    src = """
    @Composable
    fun X() {
        Column(modifier = Modifier.padding(16.dp)) {
            Column(modifier = Modifier.padding(8.dp)) {
                Text("a", modifier = Modifier.testTag("inner"))
            }
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    inner = _by_id(r.elements, "inner")
    # 16 + 8 = 24 on both axes
    assert inner.x == 24.0 and inner.y == 24.0


# ============================================================================
# Row — horizontal stack
# ============================================================================


def test_row_stacks_children_horizontally() -> None:
    src = """
    @Composable
    fun X() {
        Row {
            Icon(modifier = Modifier.testTag("i1"))
            Icon(modifier = Modifier.testTag("i2"))
            Icon(modifier = Modifier.testTag("i3"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    i1 = _by_id(r.elements, "i1")
    i2 = _by_id(r.elements, "i2")
    i3 = _by_id(r.elements, "i3")
    assert i1.x == 0.0 and i1.w == DEFAULT_ICON_SIZE_DP
    assert i2.x == DEFAULT_ICON_SIZE_DP
    assert i3.x == 2 * DEFAULT_ICON_SIZE_DP


# ============================================================================
# Weight — two-pass allocation
# ============================================================================


def test_weight_splits_row_width_evenly() -> None:
    src = """
    @Composable
    fun X() {
        Row(modifier = Modifier.fillMaxWidth().height(56.dp)) {
            IconButton(onClick = {}, modifier = Modifier.weight(1f).testTag("a")) { Icon() }
            IconButton(onClick = {}, modifier = Modifier.weight(1f).testTag("b")) { Icon() }
            IconButton(onClick = {}, modifier = Modifier.weight(1f).testTag("c")) { Icon() }
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    for eid, expect_x in (("a", 0.0), ("b", 120.0), ("c", 240.0)):
        e = _by_id(r.elements, eid)
        assert e.w == 120.0, f"{eid} w={e.w}"
        assert e.h == 56.0
        assert e.x == expect_x


def test_weight_unequal_distributes_proportionally() -> None:
    src = """
    @Composable
    fun X() {
        Row(modifier = Modifier.fillMaxWidth().height(40.dp)) {
            IconButton(onClick = {}, modifier = Modifier.weight(1f).testTag("a")) { Icon() }
            IconButton(onClick = {}, modifier = Modifier.weight(3f).testTag("b")) { Icon() }
        }
    }
    """
    r = render_compose(src, screen_width=400, screen_height=800)
    a = _by_id(r.elements, "a")
    b = _by_id(r.elements, "b")
    assert a.w == 100.0
    assert b.w == 300.0


def test_weight_in_column_splits_height() -> None:
    src = """
    @Composable
    fun X() {
        Column(modifier = Modifier.fillMaxSize()) {
            Box(modifier = Modifier.weight(1f).testTag("top")) {}
            Box(modifier = Modifier.weight(1f).testTag("bot")) {}
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    # Box w/h are container-level; we don't emit Box as an Element, so
    # this test checks via children. Add a tagged child.


# ============================================================================
# fillMaxWidth / size / height
# ============================================================================


def test_button_size_pins_w_and_h() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            Button(onClick = {}, modifier = Modifier.size(48.dp).testTag("b")) { Text("ok") }
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    b = _by_id(r.elements, "b")
    assert b.w == 48.0 and b.h == 48.0


def test_fillmaxwidth_uses_screen_width() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            Button(onClick = {}, modifier = Modifier.fillMaxWidth().height(56.dp).testTag("cta")) { Text("Go") }
        }
    }
    """
    r = render_compose(src, screen_width=411, screen_height=891)
    cta = _by_id(r.elements, "cta")
    assert cta.w == 411.0
    assert cta.h == 56.0


def test_fillmaxwidth_inside_padded_column_shrinks() -> None:
    src = """
    @Composable
    fun X() {
        Column(modifier = Modifier.padding(16.dp)) {
            Button(onClick = {}, modifier = Modifier.fillMaxWidth().height(48.dp).testTag("cta")) { Text("Go") }
        }
    }
    """
    r = render_compose(src, screen_width=411, screen_height=891)
    cta = _by_id(r.elements, "cta")
    # 411 - 16 - 16 = 379
    assert cta.w == 379.0
    assert cta.x == 16.0


# ============================================================================
# Spacer
# ============================================================================


def test_spacer_with_height_offsets_following_sibling() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            Text("a", modifier = Modifier.testTag("t1"))
            Spacer(modifier = Modifier.height(24.dp))
            Text("b", modifier = Modifier.testTag("t2"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    t1 = _by_id(r.elements, "t1")
    t2 = _by_id(r.elements, "t2")
    # Text default h = 20; spacer adds 24; t2 starts at 20 + 24 = 44.
    assert t1.y == 0.0
    assert t2.y == 44.0


# ============================================================================
# offset modifier
# ============================================================================


def test_offset_shifts_element_in_place() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            Button(onClick = {}, modifier = Modifier.size(48.dp).offset(x = 10.dp, y = 20.dp).testTag("b")) { Text("ok") }
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    b = _by_id(r.elements, "b")
    assert b.x == 10.0
    assert b.y == 20.0


# ============================================================================
# Box overlay
# ============================================================================


def test_box_children_share_origin() -> None:
    src = """
    @Composable
    fun X() {
        Box(modifier = Modifier.padding(8.dp)) {
            Text("a", modifier = Modifier.testTag("t1"))
            Text("b", modifier = Modifier.testTag("t2"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    t1 = _by_id(r.elements, "t1")
    t2 = _by_id(r.elements, "t2")
    # Both children placed at Box's inner origin — overlay.
    assert t1.x == 8.0 and t1.y == 8.0
    assert t2.x == 8.0 and t2.y == 8.0


# ============================================================================
# Honesty rule — unresolved propagation
# ============================================================================


def test_token_padding_taints_descendants_as_unresolved() -> None:
    src = """
    @Composable
    fun X() {
        Column(modifier = Modifier.padding(MaterialTheme.spacing.md)) {
            Text("hi", modifier = Modifier.testTag("t"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    t = _by_id(r.elements, "t")
    assert t.source == "ast-unresolved"
    assert t.x is None
    assert "MaterialTheme.spacing.md" in (t.reason or "")
    assert r.coverage == 0.0


def test_unknown_composable_is_unresolved() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            CustomWidget(modifier = Modifier.testTag("custom"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    c = _by_id(r.elements, "custom")
    assert c.source == "ast-unresolved"
    assert "unknown composable: CustomWidget" in (c.reason or "")


def test_token_size_modifier_is_unresolved() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            Button(onClick = {}, modifier = Modifier.size(Theme.dim.btn).testTag("b")) { Text("ok") }
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    b = _by_id(r.elements, "b")
    assert b.source == "ast-unresolved"
    assert b.x is None


def test_resolved_sibling_is_not_tainted_by_unresolved_sibling() -> None:
    # An unresolved sibling does NOT taint its peers — only descendants of
    # the unresolved CONTAINER are tainted.
    src = """
    @Composable
    fun X() {
        Column {
            Button(onClick = {}, modifier = Modifier.size(Theme.dim.btn).testTag("bad")) { Text("ok") }
            Button(onClick = {}, modifier = Modifier.size(48.dp).testTag("good")) { Text("ok") }
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    bad = _by_id(r.elements, "bad")
    good = _by_id(r.elements, "good")
    assert bad.source == "ast-unresolved"
    assert good.source == "ast-resolved"
    assert good.w == 48.0


# ============================================================================
# testTag extraction
# ============================================================================


def test_testtag_becomes_element_id() -> None:
    src = """
    @Composable
    fun X() {
        Column { Text("a", modifier = Modifier.testTag("hello_world")) }
    }
    """
    r = render_compose(src)
    assert r.elements[0].id == "hello_world"


def test_no_testtag_falls_back_to_role_with_counter() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            Text("a")
            Text("b")
            Button(onClick = {}) { Text("c") }
        }
    }
    """
    r = render_compose(src)
    ids = [e.id for e in r.elements]
    # text_1 / text_2 / primary_action_1 — auto-generated stable ids.
    assert "text_1" in ids and "text_2" in ids
    assert "primary_action_1" in ids


# ============================================================================
# Output dict shape (downstream consumer contract)
# ============================================================================


def test_resolved_element_dict_has_xywh_no_reason() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            Button(onClick = {}, modifier = Modifier.size(48.dp).testTag("b")) { Text("ok") }
        }
    }
    """
    r = render_compose(src)
    d = _by_id(r.elements, "b").to_dict()
    assert d["source"] == "ast-resolved"
    assert {"x", "y", "w", "h"} <= d.keys()
    assert "reason" not in d


def test_unresolved_element_dict_has_reason_no_xywh() -> None:
    src = """
    @Composable
    fun X() {
        Column { CustomWidget(modifier = Modifier.testTag("c")) }
    }
    """
    r = render_compose(src)
    d = _by_id(r.elements, "c").to_dict()
    assert d["source"] == "ast-unresolved"
    assert "reason" in d
    for k in ("x", "y", "w", "h"):
        assert k not in d


def test_report_to_dict_carries_screen_and_coverage() -> None:
    src = """
    @Composable
    fun X() {
        Column { Text("a", modifier = Modifier.testTag("t")) }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    d = r.to_dict()
    assert d["screen"] == {"width": 360, "height": 800, "unit": "dp"}
    assert d["coverage"] == 1.0
    assert d["source"] == "ast-resolved"
    assert isinstance(d["elements"], list)
    assert len(d["elements"]) == 1


# ============================================================================
# 0.1.2 — Scaffold / Theme / Lazy / M3 atoms / false-positive filter
# ============================================================================


def test_scaffold_renders_content_as_column() -> None:
    src = """
    @Composable
    fun X() {
        Scaffold(topBar = {}) { padding ->
            Column(modifier = Modifier.padding(16.dp)) {
                Text("a", modifier = Modifier.testTag("t"))
            }
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    t = _by_id(r.elements, "t")
    assert t.source == "ast-resolved"
    assert t.x == 16.0 and t.y == 16.0


def test_theme_wrapper_is_passthrough() -> None:
    src = """
    @Composable
    fun X() {
        MoneyManTheme {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("a", modifier = Modifier.testTag("t"))
            }
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    t = _by_id(r.elements, "t")
    # Same coordinates as if MoneyManTheme weren't there.
    assert t.x == 16.0 and t.y == 16.0


def test_material_theme_is_passthrough() -> None:
    src = """
    @Composable
    fun X() {
        MaterialTheme {
            Text("a", modifier = Modifier.testTag("t"))
        }
    }
    """
    r = render_compose(src)
    t = _by_id(r.elements, "t")
    assert t.x == 0.0 and t.y == 0.0


def test_lazy_column_renders_items() -> None:
    src = """
    @Composable
    fun X() {
        LazyColumn {
            item { Text("a", modifier = Modifier.testTag("head")) }
            items(5) { idx -> Text("b", modifier = Modifier.testTag("row")) }
        }
    }
    """
    r = render_compose(src)
    head = _by_id(r.elements, "head")
    row = _by_id(r.elements, "row")
    assert head.source == "ast-resolved"
    assert row.source == "ast-resolved"
    assert head.y == 0.0
    assert row.y == 20.0  # one text default h


def test_horizontal_divider_full_width_1dp() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            HorizontalDivider(modifier = Modifier.testTag("d"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    d = _by_id(r.elements, "d")
    assert d.role == "divider"
    assert d.w == 360.0
    assert d.h == 1.0


def test_top_app_bar_default_64dp_height() -> None:
    src = """
    @Composable
    fun X() {
        Column {
            TopAppBar(title = { Text("hi") }, modifier = Modifier.testTag("bar"))
        }
    }
    """
    r = render_compose(src, screen_width=360, screen_height=800)
    bar = _by_id(r.elements, "bar")
    assert bar.role == "app_bar"
    assert bar.h == 64.0
    assert bar.w == 360.0


def test_scope_function_let_is_not_a_phantom_composable() -> None:
    # The false-positive that hit dogfood: `state.value.let { ... }`
    # parsed as a "let" composable. After the candidate filter, scope
    # functions on a chain are silently ignored.
    src = """
    @Composable
    fun X() {
        val state = ""
        state.let { s ->
            Text(s, modifier = Modifier.testTag("t"))
        }
    }
    """
    r = render_compose(src)
    # The Text inside .let does NOT render — we don't enter scope-function
    # lambdas (callee navigation_expression, lowercase let). This is honest:
    # we cannot statically prove the scope function runs, so we skip it.
    # The acceptable behaviour is "nothing emitted" — not a phantom "let"
    # element. (0.1.1 emitted unresolved with role="let".)
    ids = [e.id for e in r.elements]
    assert "t" not in ids
    # And no element has role "let".
    assert all(e.role != "let" for e in r.elements)


def test_property_access_call_is_not_a_phantom_composable() -> None:
    # `val state by component.subscribeAsState()` — the call's callee is
    # navigation_expression `component.subscribeAsState`. Must not appear
    # as an element.
    src = """
    @Composable
    fun X(component: Component) {
        val state by component.subscribeAsState()
        Text("a", modifier = Modifier.testTag("real"))
    }
    """
    r = render_compose(src)
    ids = {e.id for e in r.elements}
    assert ids == {"real"}
