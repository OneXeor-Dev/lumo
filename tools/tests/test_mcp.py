"""Tests for the MCP server wrappers.

We don't spin up the stdio transport — the SDK tests that. We verify that
the FastMCP server registers our tools with correct names and that
each wrapper produces the same result as calling the underlying Python
API directly. That's the only Lumo-specific surface area MCP adds.
"""

from __future__ import annotations

import pytest

from lumo.mcp.server import (  # noqa: F401  (lumo_figma_diff used by test below)
    lumo_audit_scan,
    lumo_figma_diff,
    lumo_parity_diff,
    lumo_render_compose,
    lumo_render_swiftui,
    lumo_source_check_compose,
    lumo_source_check_swiftui,
    lumo_theory_check,
    lumo_wcag_check,
    lumo_wcag_fix,
    server,
)
from lumo.parity.core import diff
from lumo.render.core import render_compose, render_swiftui
from lumo.source.core import check_compose, check_swiftui
from lumo.theory.core import Element, Layout, Screen, check_layout
from lumo.wcag.core import auto_correct, check_pair


# ============================================================================
# Server registration
# ============================================================================


@pytest.mark.asyncio
async def test_server_registers_all_tools() -> None:
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "lumo_wcag_check",
        "lumo_wcag_fix",
        "lumo_theory_check",
        "lumo_parity_diff",
        "lumo_source_check_compose",
        "lumo_source_check_swiftui",
        "lumo_audit_scan",
        "lumo_figma_diff",
        "lumo_render_compose",
        "lumo_render_swiftui",
    }


@pytest.mark.asyncio
async def test_every_tool_has_a_description() -> None:
    tools = await server.list_tools()
    for tool in tools:
        assert tool.description, f"{tool.name} is missing a description"
        # Descriptions are how the LLM decides when to call. Enforce a floor
        # to catch accidental empty docstrings.
        assert len(tool.description) >= 80, (
            f"{tool.name} has a suspiciously short description "
            f"({len(tool.description)} chars)"
        )


# ============================================================================
# wcag wrappers must agree with the underlying API
# ============================================================================


def test_wcag_check_wrapper_matches_direct_call() -> None:
    direct = check_pair("#3B82F6", "#FFFFFF", "AA", "normal")
    via_mcp = lumo_wcag_check("#3B82F6", "#FFFFFF", "AA", "normal")
    assert via_mcp["fg"] == direct.fg
    assert via_mcp["bg"] == direct.bg
    assert via_mcp["ratio"] == direct.ratio
    assert via_mcp["passes"] == direct.passes


def test_wcag_fix_wrapper_matches_direct_call() -> None:
    direct = auto_correct("#7DD3FC", "#FFFFFF", "AA", "normal")
    via_mcp = lumo_wcag_fix("#7DD3FC", "#FFFFFF", "AA", "normal")
    assert via_mcp["corrected_fg"] == direct.corrected_fg
    assert via_mcp["strategy"] == direct.strategy
    assert via_mcp["iterations"] == direct.iterations


# ============================================================================
# theory wrapper accepts JSON dict and produces the same findings
# ============================================================================


def test_theory_wrapper_matches_direct_call() -> None:
    layout_dict = {
        "screen": {"width": 411, "height": 891, "unit": "dp"},
        "source": "measured",
        "elements": [
            {"id": "close", "role": "icon_button", "x": 16, "y": 24, "w": 32, "h": 32},
            {"id": "cta", "role": "primary_action", "x": 24, "y": 720, "w": 363, "h": 56, "weight": "primary"},
        ],
    }
    via_mcp = lumo_theory_check(layout_dict)

    direct_layout = Layout(
        screen=Screen(width=411, height=891, unit="dp"),
        elements=(
            Element(id="close", role="icon_button", x=16, y=24, w=32, h=32),
            Element(id="cta", role="primary_action", x=24, y=720, w=363, h=56, weight="primary"),
        ),
        source="measured",
    )
    direct = check_layout(direct_layout)

    assert via_mcp["source"] == direct.source
    assert via_mcp["counts_by_severity"] == direct.counts_by_severity
    assert len(via_mcp["findings"]) == len(direct.findings)


def test_theory_wrapper_defaults_source_when_omitted() -> None:
    """If the user forgets to declare a source, default to the most honest
    (least confident) value rather than silently claiming 'measured'."""
    layout_dict = {
        "screen": {"width": 411, "height": 891, "unit": "dp"},
        "elements": [
            {"id": "close", "role": "icon_button", "x": 16, "y": 24, "w": 32, "h": 32},
        ],
    }
    via_mcp = lumo_theory_check(layout_dict)
    assert via_mcp["source"] == "description-estimated"


# ============================================================================
# parity wrapper, including the config path
# ============================================================================


def test_parity_wrapper_matches_direct_call_no_config() -> None:
    android = {
        "screen": {"width": 411, "height": 891, "unit": "dp"},
        "source": "measured",
        "elements": [
            {"id": "cta", "role": "primary_action", "x": 24, "y": 720, "w": 363, "h": 56, "weight": "primary"},
        ],
    }
    ios = {
        "screen": {"width": 393, "height": 852, "unit": "pt"},
        "source": "measured",
        "elements": [
            {"id": "cta", "role": "primary_action", "x": 20, "y": 730, "w": 353, "h": 56, "weight": "primary"},
        ],
    }
    via_mcp = lumo_parity_diff(android, ios)
    assert via_mcp["confidence"] == "measured"
    assert any(f["check"] == "width_mismatch" for f in via_mcp["findings"])


def test_parity_wrapper_accepts_design_system_config() -> None:
    common = [
        {"id": "cta", "role": "primary_action", "x": 24, "y": 720, "w": 363, "h": 48, "weight": "primary"},
    ]
    payload = {
        "screen": {"width": 411, "height": 891, "unit": "dp"},
        "source": "measured",
        "elements": common,
    }
    via_mcp = lumo_parity_diff(
        payload,
        {**payload, "screen": {"width": 393, "height": 852, "unit": "pt"}},
        {"sizing": {"primary_button_height": 56}},
    )
    # Both platforms violate the token, both should be flagged.
    checks = {f["check"] for f in via_mcp["findings"]}
    assert "design_system_height_mismatch_android" in checks
    assert "design_system_height_mismatch_ios" in checks


# ============================================================================
# source wrapper must agree with the underlying API
# ============================================================================


def test_source_check_compose_wrapper_matches_direct_call() -> None:
    src = """
    @Composable
    fun Brand() {
        IconButton(onClick = {}, modifier = Modifier.size(20.dp)) { }
        Surface(color = Color(0xFFAA0000)) { }
        Surface(shape = RoundedCornerShape(13.dp)) { }
    }
    """
    via_mcp = lumo_source_check_compose(src, path="Brand.kt")
    direct = check_compose(src, path="Brand.kt")

    assert via_mcp["file"] == direct.file
    assert via_mcp["language"] == direct.language
    assert via_mcp["counts_by_severity"] == direct.counts_by_severity
    assert len(via_mcp["findings"]) == len(direct.findings)
    via_checks = {f["check"] for f in via_mcp["findings"]}
    assert {"undersized_tap_target", "hardcoded_color", "off_scale_radius"} <= via_checks


def test_source_wrapper_accepts_custom_scale() -> None:
    src = """
    @Composable
    fun Box() {
        Column(modifier = Modifier.padding(13.dp)) { }
    }
    """
    # 13 is on this custom scale — must not flag off_scale_spacing.
    via_mcp = lumo_source_check_compose(src, spacing_scale=[0, 13, 26])
    assert all(f["check"] != "off_scale_spacing" for f in via_mcp["findings"])


def test_source_check_swiftui_wrapper_matches_direct_call() -> None:
    # 0.0.9: tap-target finding only fires inside an interactive view.
    # Wrap the small frame in Button so all three checks fire.
    src = """
    struct Brand: View {
        var body: some View {
            Button(action: {}) { Image(systemName: "x") }
                .frame(width: 20, height: 20)
            Rectangle()
                .fill(Color(red: 0.7, green: 0, blue: 0))
                .cornerRadius(13)
        }
    }
    """
    via_mcp = lumo_source_check_swiftui(src, path="Brand.swift")
    direct = check_swiftui(src, path="Brand.swift")

    assert via_mcp["file"] == direct.file
    assert via_mcp["language"] == direct.language == "swift"
    assert via_mcp["counts_by_severity"] == direct.counts_by_severity
    assert len(via_mcp["findings"]) == len(direct.findings)
    via_checks = {f["check"] for f in via_mcp["findings"]}
    assert {"undersized_tap_target", "hardcoded_color", "off_scale_radius"} <= via_checks


def test_source_swiftui_wrapper_accepts_custom_scale() -> None:
    src = """
    struct Box: View {
        var body: some View { Text("hi").padding(13) }
    }
    """
    via_mcp = lumo_source_check_swiftui(src, spacing_scale=[0, 13, 26])
    assert all(f["check"] != "off_scale_spacing" for f in via_mcp["findings"])


# ============================================================================
# audit wrapper must agree with the underlying API
# ============================================================================


def test_audit_scan_wrapper_returns_expected_keys(tmp_path: object) -> None:
    # `tmp_path` is a pytest fixture — the function signature is `Path`,
    # but we annotate it loosely here to keep the test module independent
    # of pytest type stubs.
    import os
    from pathlib import Path as _P

    root = _P(str(tmp_path))
    (root / "Bad.kt").write_text(
        '@Composable fun B() { Column(modifier = Modifier.padding(13.dp)) {} }',
        encoding="utf-8",
    )

    via_mcp = lumo_audit_scan(str(root))

    assert via_mcp["root"] == os.fspath(root.resolve())
    assert via_mcp["files_scanned"] == 1
    assert "scale_observations" in via_mcp
    assert "counts_by_severity" in via_mcp
    assert "findings" in via_mcp
    # 13 should appear as an off-scale padding literal.
    padding_obs = next(o for o in via_mcp["scale_observations"] if o["kind"] == "padding")
    assert 13.0 in padding_obs["off_scale"]


def test_figma_diff_wrapper_uses_figma_api_and_diffs(monkeypatch: object) -> None:
    """Patch fetch_tokens at the server module level so we don't hit Figma."""
    import sys
    from lumo.figma.core import FigmaToken, FigmaTokens
    server_module = sys.modules["lumo.mcp.server"]

    fake = FigmaTokens(
        file_key="FILE",
        mode_label="default",
        colors=(),
        floats=(
            FigmaToken(
                id="1", name="spacing/lg", type="FLOAT", collection="X",
                mode_name="default", value=24.0, value_canonical=24.0,
                is_alias_resolved=True,
            ),
        ),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        server_module, "figma_fetch_tokens", lambda *a, **kw: fake
    )

    audit = {
        "scale_observations": [
            {
                "kind": "padding",
                "values_by_frequency": [{"value": 24.0, "count": 7}],
            }
        ],
        "findings": [],
    }
    out = lumo_figma_diff(file_key="FILE", audit_payload=audit)
    assert out["file_key"] == "FILE"
    assert out["summary_counts"]["matched"] == 1
    assert out["matched"][0]["token"]["name"] == "spacing/lg"
    assert out["matched"][0]["code_occurrences"] == 7


def test_audit_scan_wrapper_respects_exclude(tmp_path: object) -> None:
    from pathlib import Path as _P

    root = _P(str(tmp_path))
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "keep.kt").write_text(
        '@Composable fun K() { Column(modifier = Modifier.padding(13.dp)) {} }',
        encoding="utf-8",
    )
    (root / "tests" / "skip.kt").write_text(
        '@Composable fun S() { Column(modifier = Modifier.padding(13.dp)) {} }',
        encoding="utf-8",
    )

    via_mcp = lumo_audit_scan(str(root), exclude=["tests/**"])
    assert via_mcp["files_scanned"] == 1


# ============================================================================
# render wrappers must agree with the underlying API
# ============================================================================


_COMPOSE_LOGIN = """
@Composable
fun LoginScreen() {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Welcome", modifier = Modifier.testTag("title"))
        Spacer(modifier = Modifier.height(8.dp))
        Button(onClick = {}, modifier = Modifier.fillMaxWidth().height(48.dp).testTag("cta")) {
            Text("Continue")
        }
    }
}
"""

_SWIFTUI_LOGIN = """
struct LoginView: View {
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


def test_render_compose_wrapper_matches_direct_call() -> None:
    via_mcp = lumo_render_compose(_COMPOSE_LOGIN, screen_width=411, screen_height=891)
    direct = render_compose(_COMPOSE_LOGIN, screen_width=411, screen_height=891)
    assert via_mcp == direct.to_dict()
    # Sanity: same coordinates Compose tests already verified.
    assert via_mcp["coverage"] == 1.0
    assert via_mcp["screen"]["unit"] == "dp"
    ids = {e["id"]: e for e in via_mcp["elements"]}
    assert ids["title"]["x"] == 16.0 and ids["title"]["y"] == 16.0
    assert ids["cta"]["w"] == 379.0  # 411 - 32 padding
    assert ids["cta"]["h"] == 48.0


def test_render_swiftui_wrapper_matches_direct_call() -> None:
    via_mcp = lumo_render_swiftui(_SWIFTUI_LOGIN, screen_width=411, screen_height=891)
    direct = render_swiftui(_SWIFTUI_LOGIN, screen_width=411, screen_height=891)
    assert via_mcp == direct.to_dict()
    assert via_mcp["coverage"] == 1.0
    assert via_mcp["screen"]["unit"] == "pt"
    ids = {e["id"]: e for e in via_mcp["elements"]}
    assert ids["cta"]["w"] == 379.0
    assert ids["cta"]["h"] == 48.0


def test_render_compose_and_swiftui_via_mcp_produce_matching_topology() -> None:
    # The cross-platform parity guarantee — same logical screen, same
    # coordinates through MCP. This is the whole point of having BOTH
    # render tools in the MCP surface: clients can pair Android+iOS
    # rendering in one tool call sequence and feed the results to
    # lumo_parity_diff without manual coordinate work.
    rc = lumo_render_compose(_COMPOSE_LOGIN, screen_width=411, screen_height=891)
    rs = lumo_render_swiftui(_SWIFTUI_LOGIN, screen_width=411, screen_height=891)
    rc_ids = {e["id"]: e for e in rc["elements"]}
    rs_ids = {e["id"]: e for e in rs["elements"]}
    for key in ("title", "cta"):
        for axis in ("x", "y", "w", "h"):
            assert rc_ids[key][axis] == rs_ids[key][axis], (
                f"parity mismatch on {key}.{axis}: "
                f"compose={rc_ids[key][axis]} swiftui={rs_ids[key][axis]}"
            )


def test_render_compose_wrapper_honours_target_kwarg() -> None:
    src = """
    @Composable
    fun First() { Column { Text("a", modifier = Modifier.testTag("first")) } }
    @Composable
    fun Second() { Column { Text("b", modifier = Modifier.testTag("second")) } }
    """
    via_mcp = lumo_render_compose(src, target="Second")
    ids = {e["id"] for e in via_mcp["elements"]}
    assert ids == {"second"}


def test_render_compose_wrapper_surfaces_ast_unresolved() -> None:
    # Token references must reach the MCP client untouched, with their
    # `reason` field — that's the whole honesty contract.
    src = """
    @Composable
    fun X() {
        Column(modifier = Modifier.padding(MaterialTheme.spacing.md)) {
            Text("hi", modifier = Modifier.testTag("t"))
        }
    }
    """
    out = lumo_render_compose(src, screen_width=360, screen_height=800)
    assert out["coverage"] == 0.0
    t = next(e for e in out["elements"] if e["id"] == "t")
    assert t["source"] == "ast-unresolved"
    assert "MaterialTheme.spacing.md" in t["reason"]
    assert "x" not in t  # no fake coordinates


def test_render_swiftui_wrapper_surfaces_unknown_view() -> None:
    src = """
    struct V: View {
        var body: some View {
            VStack { CustomWidget().accessibilityIdentifier("c") }
        }
    }
    """
    out = lumo_render_swiftui(src)
    c = next(e for e in out["elements"] if e["id"] == "c")
    assert c["source"] == "ast-unresolved"
    assert "unknown view: CustomWidget" in c["reason"]
