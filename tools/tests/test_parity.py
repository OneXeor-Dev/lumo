"""Tests for platform_parity.

Each test crafts the minimum Android+iOS layout pair that should produce
exactly one expected finding (or no findings, for the parity case).
"""

from __future__ import annotations

import pytest

from lumo.parity.core import DesignSystemConfig, diff
from lumo.theory.core import Element, Layout, Screen

ANDROID_SCREEN = Screen(width=411, height=891, unit="dp")
IOS_SCREEN = Screen(width=393, height=852, unit="pt")


def _android(elements: list[Element], source: str = "measured") -> Layout:
    return Layout(screen=ANDROID_SCREEN, elements=tuple(elements), source=source)  # type: ignore[arg-type]


def _ios(elements: list[Element], source: str = "measured") -> Layout:
    return Layout(screen=IOS_SCREEN, elements=tuple(elements), source=source)  # type: ignore[arg-type]


# ============================================================================
# Identical layouts → no findings
# ============================================================================


def test_identical_layouts_yield_no_findings() -> None:
    common = [
        Element(id="cta", role="primary_action", x=24, y=720, w=363, h=56, weight="primary"),
        Element(id="title", role="text", x=24, y=80, w=300, h=32),
    ]
    report = diff(_android(list(common)), _ios(list(common)))
    assert report.findings == ()
    assert report.confidence == "measured"


# ============================================================================
# Width / height mismatch
# ============================================================================


def test_width_mismatch_is_flagged() -> None:
    android = _android([
        Element(id="cta", role="primary_action", x=24, y=720, w=363, h=56, weight="primary"),
    ])
    ios = _ios([
        Element(id="cta", role="primary_action", x=24, y=720, w=345, h=56, weight="primary"),
    ])
    report = diff(android, ios)
    mismatches = [f for f in report.findings if f.check == "width_mismatch"]
    assert len(mismatches) == 1
    assert mismatches[0].element_id == "cta"
    assert mismatches[0].android_value == 363
    assert mismatches[0].ios_value == 345


def test_height_mismatch_is_flagged() -> None:
    # Common junior bug: SwiftUI dev wrote padding(48) thinking "iOS uses 3x"
    # when Android is 16dp.
    android = _android([
        Element(id="card", role="list_item", x=24, y=200, w=363, h=16),
    ])
    ios = _ios([
        Element(id="card", role="list_item", x=24, y=200, w=363, h=48),
    ])
    report = diff(android, ios)
    height_diffs = [f for f in report.findings if f.check == "height_mismatch"]
    assert len(height_diffs) == 1
    assert "Android 16dp vs iOS 48pt" in height_diffs[0].message


# ============================================================================
# Component presence
# ============================================================================


def test_element_missing_on_ios_is_flagged_as_high() -> None:
    android = _android([
        Element(id="cta", role="primary_action", x=24, y=720, w=363, h=56, weight="primary"),
        Element(id="fab", role="primary_action", x=320, y=640, w=56, h=56, weight="primary"),
    ])
    ios = _ios([
        Element(id="cta", role="primary_action", x=24, y=720, w=363, h=56, weight="primary"),
    ])
    report = diff(android, ios)
    missing = [f for f in report.findings if f.check == "component_missing_on_ios"]
    assert len(missing) == 1
    assert missing[0].element_id == "fab"
    assert missing[0].severity == "high"


def test_element_missing_on_android_is_flagged() -> None:
    android = _android([])
    ios = _ios([
        Element(id="search_bar", role="input", x=24, y=80, w=345, h=44),
    ])
    report = diff(android, ios)
    missing = [f for f in report.findings if f.check == "component_missing_on_android"]
    assert len(missing) == 1
    assert missing[0].element_id == "search_bar"


# ============================================================================
# Whitelist: legitimate platform-specific defaults → info only
# ============================================================================


def test_touch_target_48dp_vs_44pt_is_info_not_mismatch() -> None:
    android = _android([
        Element(id="icon", role="icon_button", x=16, y=24, w=48, h=48),
    ])
    ios = _ios([
        Element(id="icon", role="icon_button", x=16, y=24, w=44, h=44),
    ])
    report = diff(android, ios)
    # Should be a single info finding, NOT a high/medium mismatch.
    assert all(f.severity == "info" for f in report.findings)
    assert any(f.check == "platform_specific_default" for f in report.findings)


def test_bottom_nav_80dp_vs_tab_bar_49pt_is_info() -> None:
    android = _android([
        Element(id="nav1", role="nav_item", x=0, y=830, w=80, h=80, group="bottom_nav"),
    ])
    ios = _ios([
        Element(id="nav1", role="nav_item", x=0, y=830, w=80, h=49, group="tab_bar"),
    ])
    report = diff(android, ios)
    info_findings = [f for f in report.findings if f.severity == "info"]
    assert info_findings, "Expected info-level whitelisted finding"
    assert any("Tab Bar" in f.message for f in info_findings)


# ============================================================================
# Design system validation
# ============================================================================


def test_design_system_height_mismatch_on_android_only() -> None:
    config = DesignSystemConfig(
        sizing={"primary_button_height": 56},
    )
    android = _android([
        Element(id="cta", role="primary_action", x=24, y=720, w=363, h=48, weight="primary"),  # wrong
    ])
    ios = _ios([
        Element(id="cta", role="primary_action", x=24, y=720, w=363, h=48, weight="primary"),  # also wrong
    ])
    report = diff(android, ios, config)
    android_ds = [f for f in report.findings if f.check == "design_system_height_mismatch_android"]
    ios_ds = [f for f in report.findings if f.check == "design_system_height_mismatch_ios"]
    assert len(android_ds) == 1
    assert len(ios_ds) == 1


def test_design_system_pass_when_both_platforms_align_to_token() -> None:
    config = DesignSystemConfig(sizing={"primary_button_height": 56})
    common = [
        Element(id="cta", role="primary_action", x=24, y=720, w=363, h=56, weight="primary"),
    ]
    report = diff(_android(list(common)), _ios(list(common)), config)
    assert report.findings == ()


# ============================================================================
# Confidence propagation: combined = worse of the two
# ============================================================================


@pytest.mark.parametrize(
    "a_source, i_source, expected",
    [
        ("measured", "measured", "measured"),
        ("measured", "code-estimated", "code-estimated"),
        ("code-estimated", "description-estimated", "description-estimated"),
        ("description-estimated", "description-estimated", "description-estimated"),
    ],
)
def test_combined_confidence_is_worse_of_two(a_source: str, i_source: str, expected: str) -> None:
    common = [Element(id="cta", role="primary_action", x=24, y=720, w=363, h=56, weight="primary")]
    report = diff(_android(list(common), source=a_source), _ios(list(common), source=i_source))
    assert report.confidence == expected


# ============================================================================
# Position differences are intentionally NOT flagged
# ============================================================================


def test_x_y_differences_are_not_flagged() -> None:
    # Same element, different x/y (legitimate due to different screen widths / insets).
    android = _android([
        Element(id="cta", role="primary_action", x=24, y=720, w=300, h=56, weight="primary"),
    ])
    ios = _ios([
        Element(id="cta", role="primary_action", x=46, y=735, w=300, h=56, weight="primary"),
    ])
    report = diff(android, ios)
    assert report.findings == ()
