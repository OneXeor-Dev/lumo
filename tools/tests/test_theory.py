"""Tests for theory_check.

Anchored against hand-built layouts that exhibit a specific failure mode.
Each test creates the minimum geometry to trigger or NOT trigger a check.
"""

from __future__ import annotations

import pytest

from lumo.theory.core import Element, Layout, Screen, check_layout


# A Pixel 7-class viewport, dp.
PIXEL_SCREEN = Screen(width=411, height=891, unit="dp")


def _layout(elements: list[Element], source: str = "measured") -> Layout:
    return Layout(screen=PIXEL_SCREEN, elements=tuple(elements), source=source)  # type: ignore[arg-type]


# ============================================================================
# Empty / trivial inputs
# ============================================================================


def test_empty_layout_yields_no_findings() -> None:
    report = check_layout(_layout([]))
    assert report.findings == ()


def test_single_button_yields_no_fitts_or_hick() -> None:
    report = check_layout(_layout([
        Element(id="ok", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ]))
    # No Fitts (need ≥2 interactive), no Hick (no group), no Gestalt (no groups),
    # no reach issue (bottom half).
    assert report.findings == ()


# ============================================================================
# Check 1 — undersized tap target
# ============================================================================


def test_undersized_target_is_flagged() -> None:
    # 32dp icon button is under Material's 48dp minimum.
    layout = _layout([
        Element(id="close", role="icon_button", x=370, y=20, w=32, h=32),
        Element(id="cta", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    undersized = [f for f in report.findings if f.check == "fitts_undersized_target"]
    assert len(undersized) == 1
    assert undersized[0].elements == ("close",)
    assert undersized[0].metric["smaller_side"] == 32
    assert undersized[0].metric["minimum"] == 48


def test_at_minimum_target_is_not_flagged() -> None:
    layout = _layout([
        Element(id="ok", role="icon_button", x=24, y=24, w=48, h=48),
        Element(id="cta", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    assert not any(f.check == "fitts_undersized_target" for f in report.findings)


# ============================================================================
# Check 1 — primary action with disproportionately high Fitts ID
# ============================================================================


def test_primary_action_disproportionately_hard() -> None:
    # All other interactive targets are large + centred. Primary is a tiny
    # button in a corner — it ends up with much higher Fitts ID than median.
    layout = _layout([
        Element(id="tab1", role="tab", x=40, y=420, w=80, h=56),
        Element(id="tab2", role="tab", x=160, y=420, w=80, h=56),
        Element(id="tab3", role="tab", x=280, y=420, w=80, h=56),
        Element(id="cta", role="primary_action", x=370, y=24, w=48, h=48, weight="primary"),
    ])
    report = check_layout(layout)
    hard = [f for f in report.findings if f.check == "fitts_difficult_primary"]
    # The primary in a top corner should trigger Fitts difficulty (it might
    # ALSO trigger reach; we only assert Fitts here).
    assert hard, f"Expected fitts_difficult_primary, got {[f.check for f in report.findings]}"
    assert hard[0].elements == ("cta",)


# ============================================================================
# Check 2 — Hick overload
# ============================================================================


def test_hick_flags_too_many_equal_choices() -> None:
    # 7 equally-weighted nav items in the same group.
    bottom_nav = [
        Element(id=f"nav{i}", role="nav_item", x=i * 58, y=830, w=58, h=56, group="bottom_nav")
        for i in range(7)
    ]
    report = check_layout(_layout(bottom_nav))
    hick = [f for f in report.findings if f.check == "hick_overload"]
    assert len(hick) == 1
    assert hick[0].metric["n"] == 7


def test_hick_not_triggered_at_ceiling() -> None:
    five = [
        Element(id=f"nav{i}", role="nav_item", x=i * 80, y=830, w=80, h=56, group="bottom_nav")
        for i in range(5)
    ]
    report = check_layout(_layout(five))
    assert not any(f.check == "hick_overload" for f in report.findings)


def test_hick_not_triggered_when_one_is_primary() -> None:
    # Mixed weights → not "equally weighted" → Hick does not apply.
    items = [
        Element(id=f"item{i}", role="nav_item", x=i * 80, y=830, w=80, h=56, group="nav", weight="equal")
        for i in range(5)
    ]
    items.append(
        Element(id="item5", role="nav_item", x=400, y=830, w=80, h=56, group="nav", weight="primary")
    )
    report = check_layout(_layout(items))
    assert not any(f.check == "hick_overload" for f in report.findings)


# ============================================================================
# Check 3 — Gestalt proximity
# ============================================================================


def test_gestalt_proximity_violation_when_groups_overlap_in_space() -> None:
    # Two "groups" placed so a member of group A is closer to group B than
    # to its own group's far member.
    elements = [
        # Group A spread vertically over 200dp
        Element(id="a1", role="text", x=24, y=100, w=80, h=20, group="A"),
        Element(id="a2", role="text", x=24, y=300, w=80, h=20, group="A"),
        # Group B placed very close to a2 — closer than a1 is to a2
        Element(id="b1", role="text", x=24, y=320, w=80, h=20, group="B"),
        Element(id="b2", role="text", x=24, y=360, w=80, h=20, group="B"),
    ]
    report = check_layout(_layout(elements))
    gestalt = [f for f in report.findings if f.check == "gestalt_proximity_violation"]
    assert gestalt, "Expected gestalt_proximity_violation for overlapping groups"


def test_gestalt_proximity_ok_when_groups_clearly_separated() -> None:
    elements = [
        Element(id="a1", role="text", x=24, y=100, w=80, h=20, group="A"),
        Element(id="a2", role="text", x=24, y=140, w=80, h=20, group="A"),
        Element(id="b1", role="text", x=24, y=500, w=80, h=20, group="B"),
        Element(id="b2", role="text", x=24, y=540, w=80, h=20, group="B"),
    ]
    report = check_layout(_layout(elements))
    assert not any(f.check == "gestalt_proximity_violation" for f in report.findings)


# ============================================================================
# Check 4 — Reach (discrete rules)
# ============================================================================


def test_reach_flags_primary_in_top_corner() -> None:
    # Primary action in the top-right corner of a phone screen.
    layout = _layout([
        Element(id="save", role="primary_action", x=350, y=24, w=48, h=48, weight="primary"),
    ])
    report = check_layout(layout)
    reach = [f for f in report.findings if f.check == "reach_primary_in_top_corner"]
    assert len(reach) == 1
    assert reach[0].severity == "high"


def test_reach_warns_primary_above_midline() -> None:
    # Primary action above midline but not in a corner — should be low severity.
    layout = _layout([
        Element(id="continue", role="primary_action", x=24, y=300, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    reach = [f for f in report.findings if f.check == "reach_primary_above_midline"]
    assert len(reach) == 1
    assert reach[0].severity == "low"


def test_reach_silent_for_bottom_primary() -> None:
    layout = _layout([
        Element(id="continue", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    assert not any(f.check.startswith("reach_") for f in report.findings)


# ============================================================================
# Confidence propagation
# ============================================================================


@pytest.mark.parametrize("source", ["measured", "code-estimated", "description-estimated"])
def test_confidence_propagates_to_every_finding(source: str) -> None:
    layout = _layout([
        Element(id="bad", role="icon_button", x=10, y=10, w=24, h=24),
        Element(id="cta", role="primary_action", x=350, y=24, w=48, h=48, weight="primary"),
    ], source=source)
    report = check_layout(layout)
    assert report.source == source
    assert report.findings, "Expected at least one finding for this layout"
    assert all(f.confidence == source for f in report.findings)


# ============================================================================
# Realistic integration scenario — Material bottom-nav screen, no issues
# ============================================================================


def test_well_designed_screen_yields_no_findings() -> None:
    elements = [
        # Bottom nav: 4 items, equally weighted, but within ceiling
        Element(id="nav_home",     role="nav_item", x=0,   y=830, w=103, h=56, group="bottom_nav"),
        Element(id="nav_search",   role="nav_item", x=103, y=830, w=103, h=56, group="bottom_nav"),
        Element(id="nav_library",  role="nav_item", x=206, y=830, w=103, h=56, group="bottom_nav"),
        Element(id="nav_profile",  role="nav_item", x=309, y=830, w=103, h=56, group="bottom_nav"),
        # Title and content, well-separated
        Element(id="title",   role="text", x=24, y=80,  w=300, h=32, group="header"),
        Element(id="sub",     role="text", x=24, y=120, w=300, h=20, group="header"),
        Element(id="card1",   role="list_item", x=24, y=200, w=363, h=120, group="content"),
        Element(id="card2",   role="list_item", x=24, y=340, w=363, h=120, group="content"),
        # Primary CTA in safe spot
        Element(id="cta",     role="primary_action", x=24, y=720, w=363, h=56, weight="primary"),
    ]
    report = check_layout(_layout(elements))
    assert report.findings == (), (
        "Well-designed screen should produce no findings, got: "
        f"{[f.check for f in report.findings]}"
    )
