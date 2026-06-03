"""Tests for theory_check.

Anchored against hand-built layouts that exhibit a specific failure mode.
Each test creates the minimum geometry to trigger or NOT trigger a check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lumo.theory.cli import _layout_from_dict
from lumo.theory.core import Element, Layout, Screen, check_layout

FIXTURES = Path(__file__).parent / "fixtures"


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


def test_tap_target_check_fires_for_single_interactive_element() -> None:
    """Tap-target is independent of Fitts relative difficulty. A single
    24dp icon button is still undersized even though Fitts (which needs
    ≥2 targets for a median) does not fire."""
    layout = _layout([
        Element(id="lone_icon", role="icon_button", x=24, y=24, w=24, h=24),
    ])
    report = check_layout(layout)
    undersized = [f for f in report.findings if f.check == "fitts_undersized_target"]
    assert len(undersized) == 1
    assert undersized[0].elements == ("lone_icon",)


def test_undersized_visible_target_without_hit_area_is_medium() -> None:
    # 32dp icon button, no hit_w/hit_h declared. We can't prove a defect
    # from geometry alone (Compose IconButton wraps content in 48dp by
    # default), so the finding fires at MEDIUM with "verify in code"
    # wording.
    layout = _layout([
        Element(id="close", role="icon_button", x=370, y=20, w=32, h=32),
        Element(id="cta", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    undersized = [f for f in report.findings if f.check == "fitts_undersized_target"]
    assert len(undersized) == 1
    assert undersized[0].elements == ("close",)
    assert undersized[0].severity == "medium"
    assert "verify the touch container" in undersized[0].message.lower()
    assert undersized[0].metric["smaller_side"] == 32
    assert undersized[0].metric["minimum"] == 48


def test_undersized_declared_hit_area_is_high() -> None:
    # hit_w/hit_h explicitly declared under 48dp — definite fail, HIGH.
    layout = _layout([
        Element(
            id="bare_icon", role="icon_button",
            x=370, y=20, w=24, h=24,
            hit_w=32, hit_h=32,
        ),
        Element(id="cta", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    undersized = [f for f in report.findings if f.check == "fitts_undersized_target"]
    assert len(undersized) == 1
    assert undersized[0].severity == "high"
    assert undersized[0].metric["smaller_side"] == 32


def test_declared_hit_area_above_minimum_clears_small_visible_glyph() -> None:
    # The Material IconButton pattern: 24dp visible glyph inside a 48dp
    # invisible hit area. This is CORRECT and must not be flagged.
    layout = _layout([
        Element(
            id="back_arrow", role="icon_button",
            x=12, y=64, w=24, h=24,
            hit_w=48, hit_h=48,
        ),
        Element(id="cta", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    assert not any(f.check == "fitts_undersized_target" for f in report.findings), (
        "24dp glyph inside 48dp hit area must not trigger fitts_undersized_target"
    )


def test_at_minimum_target_is_not_flagged() -> None:
    layout = _layout([
        Element(id="ok", role="icon_button", x=24, y=24, w=48, h=48),
        Element(id="cta", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    assert not any(f.check == "fitts_undersized_target" for f in report.findings)


def test_hit_area_partially_declared_uses_visible_dim_for_missing_axis() -> None:
    # hit_w declared (48), hit_h not (falls back to h=24). Smaller side is
    # 24, still under minimum — should fire HIGH because the author DID
    # declare intent for one axis.
    layout = _layout([
        Element(
            id="thin_strip", role="icon_button",
            x=12, y=64, w=24, h=24,
            hit_w=48,  # hit_h omitted → falls back to h=24
        ),
        Element(id="cta", role="primary_action", x=24, y=800, w=363, h=56, weight="primary"),
    ])
    report = check_layout(layout)
    undersized = [f for f in report.findings if f.check == "fitts_undersized_target"]
    assert len(undersized) == 1
    assert undersized[0].severity == "high"
    assert undersized[0].metric["smaller_side"] == 24


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


def test_gestalt_skips_nested_container_pairs() -> None:
    """0.2.1: nested containers (outer fully containing inner) must NOT
    trigger gestalt_proximity_violation. Real Plazo dogfood revealed
    207 false positives from Scaffold > Column > Card hierarchies. The
    eye reads them as nesting, not as competing peers."""
    elements = [
        # Outer "container" group spans the whole screen
        Element(id="outer_a", role="decorative", x=0,  y=0,  w=400, h=800, group="container"),
        Element(id="outer_b", role="decorative", x=0,  y=0,  w=400, h=800, group="container"),
        # Inner "card" group sits ENTIRELY inside outer
        Element(id="inner_a", role="list_item",  x=16, y=16, w=368, h=120, group="card"),
        Element(id="inner_b", role="list_item",  x=16, y=16, w=368, h=120, group="card"),
    ]
    report = check_layout(_layout(elements))
    proximity_findings = [f for f in report.findings if f.check == "gestalt_proximity_violation"]
    assert proximity_findings == [], (
        "Nested container pair should be skipped, got: "
        f"{[(f.check, f.elements) for f in proximity_findings]}"
    )


def test_gestalt_still_fires_on_true_sibling_groups_too_close() -> None:
    """Regression guard: real Gestalt violations between SIBLING groups
    (neither containing the other) still trip the check after the
    nested-skip fix.

    Geometry: each group spans 400dp vertically (max_intra by centroid
    ≈ 400). The two groups sit side-by-side with only 20dp gap (min_inter
    ≈ 20). Neither bbox contains the other → nested-skip does not apply,
    and the proximity check fires.
    """
    elements = [
        # Left group: members 400dp apart vertically
        Element(id="left_a",  role="decorative", x=0,  y=0,   w=10, h=10, group="left"),
        Element(id="left_b",  role="decorative", x=0,  y=400, w=10, h=10, group="left"),
        # Right group: parallel, 20dp to the right
        Element(id="right_a", role="decorative", x=20, y=0,   w=10, h=10, group="right"),
        Element(id="right_b", role="decorative", x=20, y=400, w=10, h=10, group="right"),
    ]
    report = check_layout(_layout(elements))
    proximity_findings = [f for f in report.findings if f.check == "gestalt_proximity_violation"]
    assert len(proximity_findings) >= 1, (
        "Genuine sibling-group proximity violation should still fire"
    )


# ============================================================================
# Check 5 — Color contrast (0.2.2)
# ============================================================================


def test_contrast_check_fires_high_when_text_fails_aa() -> None:
    # #888888 on #FFFFFF ≈ 3.5:1 — fails AA (needs 4.5:1).
    layout = _layout([
        Element(
            id="grey_label", role="text", x=24, y=200, w=300, h=20,
            fg="#888888", bg="#FFFFFF",
        ),
    ])
    report = check_layout(layout)
    contrast = [f for f in report.findings if f.check == "fitts_color_contrast"]
    assert len(contrast) == 1
    assert contrast[0].severity == "high"
    assert contrast[0].elements == ("grey_label",)
    assert contrast[0].metric["required"] == 4.5


def test_contrast_check_fires_medium_when_text_passes_aa_but_fails_aaa() -> None:
    # #595959 on #FFFFFF ≈ 7.0:1 — passes AA, sits right at AAA boundary.
    # Use a slightly lighter grey to ensure we land between thresholds.
    # #6E6E6E on #FFFFFF ≈ 5.0:1 — passes AA (≥4.5), fails AAA (<7.0).
    layout = _layout([
        Element(
            id="caption", role="text", x=24, y=200, w=300, h=20,
            fg="#6E6E6E", bg="#FFFFFF",
        ),
    ])
    report = check_layout(layout)
    contrast = [f for f in report.findings if f.check == "fitts_color_contrast"]
    assert len(contrast) == 1
    assert contrast[0].severity == "medium"
    assert contrast[0].metric["required"] == 7.0


def test_contrast_check_silent_when_text_passes_aaa() -> None:
    # #000000 on #FFFFFF = 21:1 — passes both AA and AAA.
    layout = _layout([
        Element(
            id="body", role="text", x=24, y=200, w=300, h=20,
            fg="#000000", bg="#FFFFFF",
        ),
    ])
    report = check_layout(layout)
    assert not any(f.check == "fitts_color_contrast" for f in report.findings)


def test_contrast_check_skips_when_fg_or_bg_missing() -> None:
    # Honesty rule: no fill → no check (no false-positive on transparent text).
    layout = _layout([
        Element(id="fg_only", role="text", x=24, y=200, w=300, h=20, fg="#000000"),
        Element(id="bg_only", role="text", x=24, y=240, w=300, h=20, bg="#FFFFFF"),
        Element(id="neither", role="text", x=24, y=280, w=300, h=20),
    ])
    report = check_layout(layout)
    assert not any(f.check == "fitts_color_contrast" for f in report.findings)


def test_contrast_check_ignores_non_text_roles() -> None:
    # Buttons / icons / images get fg/bg from Figma walker too but contrast
    # check is text-only (button surface contrast is a different question).
    layout = _layout([
        Element(
            id="btn", role="primary_action", x=24, y=800, w=363, h=56,
            weight="primary", fg="#888888", bg="#FFFFFF",
        ),
        Element(
            id="icon", role="icon_button", x=350, y=24, w=48, h=48,
            fg="#888888", bg="#FFFFFF",
        ),
    ])
    report = check_layout(layout)
    assert not any(f.check == "fitts_color_contrast" for f in report.findings)


def test_contrast_finding_recommendation_mentions_lumo_wcag_fix() -> None:
    """The recommendation should hand the user the exact lumo-wcag CLI
    invocation that auto-fixes their colour pair — closing the loop from
    audit finding → actionable fix in one copy-paste."""
    layout = _layout([
        Element(
            id="bad", role="text", x=24, y=200, w=300, h=20,
            fg="#888888", bg="#FFFFFF",
        ),
    ])
    report = check_layout(layout)
    contrast = [f for f in report.findings if f.check == "fitts_color_contrast"]
    assert contrast
    rec = contrast[0].recommendation
    assert "lumo-wcag fix" in rec
    assert "#888888" in rec
    assert "#FFFFFF" in rec


# ============================================================================
# Fixture-driven smoke — confirmation screen with IconButton hit-area patterns
# ============================================================================


def test_fixture_confirm_screen_with_iconbutton_produces_expected_findings() -> None:
    """End-to-end against the confirmation-screen fixture. Locks in:
      - Material IconButton pattern (24dp glyph + 48dp hit area) is silent.
      - Bare undersized icon without hit_w/hit_h fires MEDIUM "verify in code".
      - Full-width primary CTA at the bottom is silent.
    """
    payload = json.loads((FIXTURES / "confirm_screen_with_iconbutton.json").read_text())
    layout = _layout_from_dict(payload)
    report = check_layout(layout)

    findings_by_check = {(f.check, f.elements[0]): f for f in report.findings}

    assert ("fitts_undersized_target", "info_icon_bare_no_hit_area") in findings_by_check
    info_finding = findings_by_check[("fitts_undersized_target", "info_icon_bare_no_hit_area")]
    assert info_finding.severity == "medium"

    # Material IconButton + primary CTA must not trigger anything.
    silent_ids = {"back_arrow_material_iconbutton", "confirm_button"}
    triggered = {f.elements[0] for f in report.findings} & silent_ids
    assert not triggered, f"Expected silence on {silent_ids}, got findings for {triggered}"
