"""Tests for lumo.render — SwiftUI front-end.

Mirrors test_render.py for SwiftUI. Each test takes a small SwiftUI
snippet with a hand-computed expected layout, renders it, and asserts
coordinates. The honesty rule is enforced explicitly: token references
and unknown views MUST emit `ast-unresolved` (never invented numbers).
"""

from __future__ import annotations

from lumo.render.core import (
    DEFAULT_BUTTON_HEIGHT_PT,
    DEFAULT_ICON_SIZE_PT,
    Element,
    render_swiftui,
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
    r = render_swiftui("")
    assert r.elements == ()


def test_no_view_struct_yields_no_elements() -> None:
    r = render_swiftui("func helper(_ x: Int) -> Int { x + 1 }")
    assert r.elements == ()


def test_target_picks_named_view() -> None:
    src = """
    struct A: View {
        var body: some View { Text("a").accessibilityIdentifier("ta") }
    }
    struct B: View {
        var body: some View { Text("b").accessibilityIdentifier("tb") }
    }
    """
    r = render_swiftui(src, target="B")
    assert {e.id for e in r.elements} == {"tb"}


def test_first_view_used_when_no_target() -> None:
    src = """
    struct A: View {
        var body: some View { Text("a").accessibilityIdentifier("ta") }
    }
    struct B: View {
        var body: some View { Text("b").accessibilityIdentifier("tb") }
    }
    """
    r = render_swiftui(src)
    assert {e.id for e in r.elements} == {"ta"}


def test_unit_is_pt_for_swiftui() -> None:
    r = render_swiftui("""
    struct V: View {
        var body: some View { Text("a") }
    }
    """, screen_width=375, screen_height=812)
    assert r.unit == "pt"
    assert r.to_dict()["screen"]["unit"] == "pt"


# ============================================================================
# VStack — vertical stack with padding
# ============================================================================


def test_vstack_with_padding_offsets_origin() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Text("a").accessibilityIdentifier("t1")
                Text("b").accessibilityIdentifier("t2")
            }.padding(16)
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    t1 = _by_id(r.elements, "t1")
    t2 = _by_id(r.elements, "t2")
    assert t1.source == "ast-resolved"
    assert t1.x == 16.0 and t1.y == 16.0
    assert t2.x == 16.0 and t2.y == 36.0  # text default h=20


def test_padding_horizontal_edge() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Text("a").accessibilityIdentifier("t")
            }.padding(.horizontal, 8).padding(.vertical, 4)
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    t = _by_id(r.elements, "t")
    assert t.x == 8.0 and t.y == 4.0


def test_padding_leading_only() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Text("a").accessibilityIdentifier("t")
            }.padding(.leading, 12)
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    t = _by_id(r.elements, "t")
    assert t.x == 12.0 and t.y == 0.0


def test_nested_stacks_accumulate_padding() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                VStack {
                    Text("a").accessibilityIdentifier("inner")
                }.padding(8)
            }.padding(16)
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    inner = _by_id(r.elements, "inner")
    assert inner.x == 24.0 and inner.y == 24.0


# ============================================================================
# HStack — horizontal stack
# ============================================================================


def test_hstack_stacks_children_horizontally() -> None:
    src = """
    struct V: View {
        var body: some View {
            HStack {
                Image(systemName: "a").accessibilityIdentifier("i1")
                Image(systemName: "b").accessibilityIdentifier("i2")
                Image(systemName: "c").accessibilityIdentifier("i3")
            }
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    i1 = _by_id(r.elements, "i1")
    i2 = _by_id(r.elements, "i2")
    i3 = _by_id(r.elements, "i3")
    assert i1.x == 0.0 and i1.w == DEFAULT_ICON_SIZE_PT
    assert i2.x == DEFAULT_ICON_SIZE_PT
    assert i3.x == 2 * DEFAULT_ICON_SIZE_PT


# ============================================================================
# .frame — explicit sizing
# ============================================================================


def test_frame_pins_width_and_height() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Button(action: {}) { Text("OK") }
                    .frame(width: 48, height: 48)
                    .accessibilityIdentifier("b")
            }
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    b = _by_id(r.elements, "b")
    assert b.w == 48.0 and b.h == 48.0


def test_frame_max_width_infinity_fills_parent() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Button(action: {}) { Text("Go") }
                    .frame(maxWidth: .infinity, minHeight: 56)
                    .accessibilityIdentifier("cta")
            }
        }
    }
    """
    r = render_swiftui(src, screen_width=411, screen_height=891)
    cta = _by_id(r.elements, "cta")
    assert cta.w == 411.0
    # minHeight is ignored in v1 — height defaults to HIG button height.
    assert cta.h == DEFAULT_BUTTON_HEIGHT_PT


def test_frame_max_width_infinity_inside_padded_stack_shrinks() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Button(action: {}) { Text("Go") }
                    .frame(maxWidth: .infinity, height: 48)
                    .accessibilityIdentifier("cta")
            }.padding(16)
        }
    }
    """
    r = render_swiftui(src, screen_width=411, screen_height=891)
    cta = _by_id(r.elements, "cta")
    assert cta.w == 379.0  # 411 - 32
    assert cta.x == 16.0
    assert cta.h == 48.0


# ============================================================================
# Spacer — axis-flex semantics
# ============================================================================


def test_spacer_with_explicit_height_offsets_following_sibling() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Text("a").accessibilityIdentifier("t1")
                Spacer().frame(height: 24)
                Text("b").accessibilityIdentifier("t2")
            }
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    t1 = _by_id(r.elements, "t1")
    t2 = _by_id(r.elements, "t2")
    assert t1.y == 0.0
    # text default h=20, spacer 24, t2 starts at 44
    assert t2.y == 44.0


def test_bare_spacer_takes_remaining_axis_extent() -> None:
    # Bare Spacer() in a VStack with a fixed parent height should push
    # the second child to the bottom of the available space.
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Text("top").accessibilityIdentifier("top")
                Spacer()
                Text("bottom").accessibilityIdentifier("bottom")
            }.frame(height: 100)
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    top = _by_id(r.elements, "top")
    bottom = _by_id(r.elements, "bottom")
    assert top.y == 0.0
    # text default h=20, two of them used 40, free = 100-40 = 60 → spacer
    # gets 60, so bottom starts at 20 + 60 = 80.
    assert bottom.y == 80.0


# ============================================================================
# .offset
# ============================================================================


def test_offset_shifts_element_in_place() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Button(action: {}) { Text("OK") }
                    .frame(width: 48, height: 48)
                    .offset(x: 10, y: 20)
                    .accessibilityIdentifier("b")
            }
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    b = _by_id(r.elements, "b")
    assert b.x == 10.0
    assert b.y == 20.0


# ============================================================================
# ZStack overlay
# ============================================================================


def test_zstack_children_share_origin() -> None:
    src = """
    struct V: View {
        var body: some View {
            ZStack {
                Text("a").accessibilityIdentifier("t1")
                Text("b").accessibilityIdentifier("t2")
            }.padding(8)
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    t1 = _by_id(r.elements, "t1")
    t2 = _by_id(r.elements, "t2")
    assert t1.x == 8.0 and t1.y == 8.0
    assert t2.x == 8.0 and t2.y == 8.0


# ============================================================================
# Honesty rule — unresolved propagation
# ============================================================================


def test_token_padding_taints_descendants_as_unresolved() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Text("hi").accessibilityIdentifier("t")
            }.padding(Theme.spacing.md)
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    t = _by_id(r.elements, "t")
    assert t.source == "ast-unresolved"
    assert t.x is None
    assert "Theme.spacing.md" in (t.reason or "")


def test_unknown_view_is_unresolved() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                CustomWidget().accessibilityIdentifier("custom")
            }
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    c = _by_id(r.elements, "custom")
    assert c.source == "ast-unresolved"
    assert "unknown view: CustomWidget" in (c.reason or "")


def test_token_frame_modifier_is_unresolved() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Button(action: {}) { Text("OK") }
                    .frame(width: Theme.dim.btn, height: Theme.dim.btn)
                    .accessibilityIdentifier("b")
            }
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    b = _by_id(r.elements, "b")
    assert b.source == "ast-unresolved"
    assert b.x is None


def test_resolved_sibling_is_not_tainted_by_unresolved_sibling() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Button(action: {}) { Text("OK") }
                    .frame(width: Theme.dim.btn, height: 44)
                    .accessibilityIdentifier("bad")
                Button(action: {}) { Text("Go") }
                    .frame(width: 48, height: 48)
                    .accessibilityIdentifier("good")
            }
        }
    }
    """
    r = render_swiftui(src, screen_width=360, screen_height=800)
    bad = _by_id(r.elements, "bad")
    good = _by_id(r.elements, "good")
    assert bad.source == "ast-unresolved"
    assert good.source == "ast-resolved"
    assert good.w == 48.0


# ============================================================================
# accessibilityIdentifier extraction
# ============================================================================


def test_accessibility_identifier_becomes_element_id() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Text("a").accessibilityIdentifier("hello_world")
            }
        }
    }
    """
    r = render_swiftui(src)
    ids = [e.id for e in r.elements]
    assert "hello_world" in ids


def test_no_accessibility_identifier_falls_back_to_role_with_counter() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack {
                Text("a")
                Text("b")
                Button(action: {}) { Text("c") }
            }
        }
    }
    """
    r = render_swiftui(src)
    ids = [e.id for e in r.elements]
    assert "text_1" in ids and "text_2" in ids
    assert "primary_action_1" in ids


# ============================================================================
# Cross-platform parity sanity (the whole point of SwiftUI render)
# ============================================================================


def test_login_screen_compose_and_swiftui_produce_matching_topology() -> None:
    # Same screen, two platforms: VStack/Column with title + cta button.
    # The honesty diff: Android default button height is 40dp, iOS HIG is
    # 44pt — both express the same INTENT ("primary action"). The CTA
    # height differs by 4 pt; that's the platform whitelist parity expects.
    from lumo.render.core import render_compose

    compose_src = """
    @Composable
    fun Login() {
        Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
            Text("Welcome", modifier = Modifier.testTag("title"))
            Spacer(modifier = Modifier.height(8.dp))
            Button(onClick = {}, modifier = Modifier.fillMaxWidth().height(48.dp).testTag("cta")) {
                Text("Continue")
            }
        }
    }
    """
    swiftui_src = """
    struct Login: View {
        var body: some View {
            VStack {
                Text("Welcome").accessibilityIdentifier("title")
                Spacer().frame(height: 8)
                Button(action: {}) { Text("Continue") }
                    .frame(maxWidth: .infinity, height: 48)
                    .accessibilityIdentifier("cta")
            }.padding(16)
        }
    }
    """
    rc = render_compose(compose_src, screen_width=411, screen_height=891)
    rs = render_swiftui(swiftui_src, screen_width=411, screen_height=891)

    # Same elements, same coordinates — modulo unit label.
    rc_title = _by_id(rc.elements, "title")
    rs_title = _by_id(rs.elements, "title")
    assert (rc_title.x, rc_title.y) == (rs_title.x, rs_title.y)

    rc_cta = _by_id(rc.elements, "cta")
    rs_cta = _by_id(rs.elements, "cta")
    assert (rc_cta.x, rc_cta.y, rc_cta.w, rc_cta.h) == (rs_cta.x, rs_cta.y, rs_cta.w, rs_cta.h)
