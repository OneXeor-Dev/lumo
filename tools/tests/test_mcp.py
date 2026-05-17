"""Tests for the MCP server wrappers.

We don't spin up the stdio transport — the SDK tests that. We verify that
the FastMCP server registers our tools with correct names and that
each wrapper produces the same result as calling the underlying Python
API directly. That's the only Lumo-specific surface area MCP adds.
"""

from __future__ import annotations

import pytest

from lumo.mcp.server import (
    lumo_parity_diff,
    lumo_source_check_compose,
    lumo_theory_check,
    lumo_wcag_check,
    lumo_wcag_fix,
    server,
)
from lumo.parity.core import diff
from lumo.source.core import check_compose
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
