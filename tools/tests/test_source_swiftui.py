"""Tests for lumo.source SwiftUI checks (check_swiftui).

Each check has at least one POSITIVE case (must flag) and one NEGATIVE
case (must not flag). Honesty rule is enforced explicitly: token / variable
references must never produce findings.
"""

from __future__ import annotations

from lumo.source.core import (
    DEFAULT_RADIUS_SCALE_DP,
    DEFAULT_SPACING_SCALE_DP,
    check_swiftui,
)


def _findings_by_check(source: str, check: str) -> list:
    report = check_swiftui(source, path="Test.swift")
    return [f for f in report.findings if f.check == check]


# ============================================================================
# Trivial inputs
# ============================================================================


def test_empty_source_yields_no_findings() -> None:
    report = check_swiftui("", path="Empty.swift")
    assert report.findings == ()
    assert report.language == "swift"
    assert report.file == "Empty.swift"


def test_file_without_swiftui_yields_no_findings() -> None:
    source = """
    import Foundation

    func add(_ a: Int, _ b: Int) -> Int { a + b }
    """
    report = check_swiftui(source)
    assert report.findings == ()


# ============================================================================
# Check 1 — undersized_tap_target  (a11y, HIG 44pt)
# ============================================================================


def test_undersized_frame_is_flagged() -> None:
    source = """
    struct Close: View {
        var body: some View {
            Button(action: {}) { Image(systemName: "xmark") }
                .frame(width: 32, height: 32)
        }
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1
    assert findings[0].category == "a11y"
    assert findings[0].severity == "high"
    assert findings[0].metric["minimum_pt"] == 44.0


def test_at_minimum_frame_is_not_flagged() -> None:
    source = """
    struct Close: View {
        var body: some View {
            Button(action: {}) { Image(systemName: "xmark") }
                .frame(width: 44, height: 44)
        }
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_token_frame_reference_is_not_flagged() -> None:
    # `Theme.dim.icon` is a token — we cannot resolve it, so we MUST NOT flag.
    source = """
    struct Themed: View {
        var body: some View {
            Image(systemName: "xmark")
                .frame(width: Theme.dim.icon, height: Theme.dim.icon)
        }
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_single_undersized_dimension_alone_is_not_flagged() -> None:
    # `.frame(width: 32)` without a height is ambiguous (might be inside a
    # larger fixed-height row) — we only flag when BOTH dimensions are
    # literal and both undersized.
    source = """
    struct Strip: View {
        var body: some View {
            Image(systemName: "xmark").frame(width: 32)
        }
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_decorative_image_frame_is_not_flagged() -> None:
    # 0.0.9: a small `Image` with no interactive ancestor is decorative,
    # not an undersized tap target. HIG's 44pt rule is for tap targets.
    source = """
    struct Logo: View {
        var body: some View {
            Image(systemName: "star")
                .frame(width: 20, height: 20)
        }
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_decorative_rectangle_frame_is_not_flagged() -> None:
    source = """
    struct Dot: View {
        var body: some View {
            Rectangle().frame(width: 8, height: 8)
        }
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_onTapGesture_frame_is_flagged() -> None:
    # `.onTapGesture {…}` turns ANY view into a tap target — a 20×20
    # frame on it is a real a11y finding.
    source = """
    struct TappableDot: View {
        var body: some View {
            Rectangle()
                .frame(width: 20, height: 20)
                .onTapGesture { /* go */ }
        }
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1


def test_navigationlink_frame_is_flagged() -> None:
    source = """
    struct NL: View {
        var body: some View {
            NavigationLink(destination: Text("x")) { Image(systemName: "chevron.right") }
                .frame(width: 20, height: 20)
        }
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1


def test_toggle_frame_is_flagged() -> None:
    source = """
    struct T: View {
        @State var on = false
        var body: some View {
            Toggle("Switch", isOn: $on).frame(width: 30, height: 30)
        }
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1


def test_snippet_is_short_and_single_line() -> None:
    # 0.0.9: SwiftUI snippets used to include the whole receiver chain.
    # Now the finding's snippet is just `.padding(13)` — short, one line.
    source = """
    struct Box: View {
        var body: some View {
            Text("hi").padding(13)
        }
    }
    """
    findings = _findings_by_check(source, "off_scale_spacing")
    assert len(findings) == 1
    snippet = findings[0].snippet
    assert snippet == ".padding(13)"
    assert "Text" not in snippet
    assert "\n" not in snippet


def test_undersized_frame_snippet_is_short() -> None:
    source = """
    struct X: View {
        var body: some View {
            Button(action: {}) { Image(systemName: "x") }.frame(width: 20, height: 20)
        }
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1
    snippet = findings[0].snippet
    # Just the offending modifier, no `Button { ... }` prefix.
    assert "frame" in snippet
    assert "20" in snippet
    assert "Button" not in snippet
    assert "Image" not in snippet
    assert "\n" not in snippet


# ============================================================================
# Check 2 — off_scale_spacing  (consistency)
# ============================================================================


def test_off_scale_padding_is_flagged() -> None:
    source = """
    struct Box: View {
        var body: some View { Text("hi").padding(13) }
    }
    """
    findings = _findings_by_check(source, "off_scale_spacing")
    assert len(findings) == 1
    assert findings[0].category == "consistency"
    assert findings[0].metric["value_pt"] == 13.0


def test_on_scale_padding_is_not_flagged() -> None:
    source = """
    struct Box: View {
        var body: some View { Text("hi").padding(16) }
    }
    """
    assert _findings_by_check(source, "off_scale_spacing") == []


def test_padding_with_edge_and_off_scale_value_is_flagged() -> None:
    source = """
    struct Box: View {
        var body: some View { Text("hi").padding(.horizontal, 13) }
    }
    """
    findings = _findings_by_check(source, "off_scale_spacing")
    assert len(findings) == 1
    assert findings[0].metric["value_pt"] == 13.0


def test_padding_with_edge_and_on_scale_value_is_not_flagged() -> None:
    source = """
    struct Box: View {
        var body: some View { Text("hi").padding(.horizontal, 16) }
    }
    """
    assert _findings_by_check(source, "off_scale_spacing") == []


def test_token_padding_value_is_not_flagged() -> None:
    source = """
    struct Box: View {
        var body: some View { Text("hi").padding(Theme.spacing.md) }
    }
    """
    assert _findings_by_check(source, "off_scale_spacing") == []


def test_default_padding_with_no_args_is_not_flagged() -> None:
    # `.padding()` uses the system default (16pt). No literal to check.
    source = """
    struct Box: View {
        var body: some View { Text("hi").padding() }
    }
    """
    assert _findings_by_check(source, "off_scale_spacing") == []


# ============================================================================
# Check 3 — hardcoded_color  (token)
# ============================================================================


def test_hardcoded_rgb_color_is_flagged() -> None:
    source = """
    struct Brand: View {
        var body: some View {
            Rectangle().fill(Color(red: 1.0, green: 0, blue: 0))
        }
    }
    """
    findings = _findings_by_check(source, "hardcoded_color")
    assert len(findings) == 1
    assert findings[0].category == "token"
    assert findings[0].metric["hex"] == "#FF0000"


def test_hardcoded_srgb_color_is_flagged() -> None:
    # `Color(.sRGB, red:..., green:..., blue:...)` — the leading
    # `.sRGB` is unlabelled but is a prefix_expression we skip.
    source = """
    struct Brand: View {
        var body: some View {
            Rectangle().fill(Color(.sRGB, red: 0.231, green: 0.510, blue: 0.965))
        }
    }
    """
    findings = _findings_by_check(source, "hardcoded_color")
    assert len(findings) == 1


def test_named_color_constant_is_not_flagged() -> None:
    source = """
    struct Brand: View {
        var body: some View {
            Rectangle().fill(Color.red)
        }
    }
    """
    assert _findings_by_check(source, "hardcoded_color") == []


def test_asset_catalog_color_is_not_flagged() -> None:
    # `Color("brandPrimary")` looks up an asset-catalog colour — treated
    # as a token. Honest behaviour: skip.
    source = """
    struct Brand: View {
        var body: some View {
            Rectangle().fill(Color("brandPrimary"))
        }
    }
    """
    assert _findings_by_check(source, "hardcoded_color") == []


def test_color_with_token_channel_is_not_flagged() -> None:
    source = """
    struct Brand: View {
        var body: some View {
            Rectangle().fill(Color(red: theme.r, green: 0, blue: 0))
        }
    }
    """
    assert _findings_by_check(source, "hardcoded_color") == []


def test_color_literal_in_colors_swift_file_is_not_flagged() -> None:
    # 0.0.9 honesty rule: literals inside the design-system colour layer
    # are intentional. `Colors.swift` / `Palette.swift` define tokens.
    source = """
    extension Color {
        static let brandPrimary = Color(red: 0.23, green: 0.51, blue: 0.96)
        static let brandSurface = Color(red: 0.98, green: 0.98, blue: 0.98)
    }
    """
    report = check_swiftui(source, path="DesignSystem/Colors.swift")
    assert [f for f in report.findings if f.check == "hardcoded_color"] == []


def test_color_literal_in_consumer_swift_file_is_still_flagged() -> None:
    source = """
    struct LoginButton: View {
        var body: some View {
            Button("Sign in") {}.foregroundColor(Color(red: 0.23, green: 0.51, blue: 0.96))
        }
    }
    """
    report = check_swiftui(source, path="Features/Login/LoginButton.swift")
    findings = [f for f in report.findings if f.check == "hardcoded_color"]
    assert len(findings) == 1


# ============================================================================
# Check 4 — off_scale_radius  (consistency)
# ============================================================================


def test_off_scale_corner_radius_is_flagged() -> None:
    source = """
    struct Card: View {
        var body: some View { Rectangle().cornerRadius(13) }
    }
    """
    findings = _findings_by_check(source, "off_scale_radius")
    assert len(findings) == 1
    assert findings[0].category == "consistency"
    assert findings[0].metric["value_pt"] == 13.0


def test_on_scale_corner_radius_is_not_flagged() -> None:
    source = """
    struct Card: View {
        var body: some View { Rectangle().cornerRadius(12) }
    }
    """
    assert _findings_by_check(source, "off_scale_radius") == []


def test_token_corner_radius_is_not_flagged() -> None:
    source = """
    struct Card: View {
        var body: some View { Rectangle().cornerRadius(Theme.radius.md) }
    }
    """
    assert _findings_by_check(source, "off_scale_radius") == []


# ============================================================================
# Report aggregation
# ============================================================================


def test_findings_are_sorted_by_severity() -> None:
    # 0.0.9: tap-target finding only fires when the frame is on an
    # interactive view — wrap the small frame in Button so all three
    # checks fire and we can verify sort order.
    source = """
    struct All: View {
        var body: some View {
            Button(action: {}) { Image(systemName: "x") }
                .frame(width: 20, height: 20)
            Rectangle()
                .fill(Color(red: 0.5, green: 0, blue: 0))
                .cornerRadius(13)
        }
    }
    """
    report = check_swiftui(source)
    severities = [f.severity for f in report.findings]
    assert severities == sorted(
        severities,
        key=lambda s: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[s],
    )
    checks = {f.check for f in report.findings}
    assert "undersized_tap_target" in checks
    assert "hardcoded_color" in checks
    assert "off_scale_radius" in checks


def test_custom_spacing_scale_changes_findings() -> None:
    source = """
    struct Box: View {
        var body: some View { Text("hi").padding(13) }
    }
    """
    report = check_swiftui(source, spacing_scale=(0, 13, 26))
    assert all(f.check != "off_scale_spacing" for f in report.findings)


def test_default_scales_apply_to_swiftui() -> None:
    # Both Compose and SwiftUI share the same spacing/radius defaults
    # because dp and pt are physically equal. Sanity-check that.
    assert isinstance(DEFAULT_SPACING_SCALE_DP, tuple)
    assert isinstance(DEFAULT_RADIUS_SCALE_DP, tuple)
