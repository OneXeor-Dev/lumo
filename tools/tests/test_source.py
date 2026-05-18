"""Tests for lumo.source — AST-based design-system drift checks for Compose.

Each check has at least one POSITIVE case (must flag) and one NEGATIVE case
(must not flag). The honesty rule is enforced explicitly: token references
like `MaterialTheme.spacing.md.dp` and `MaterialTheme.colorScheme.primary`
must never produce findings.
"""

from __future__ import annotations

import pytest

from lumo.source.core import (
    DEFAULT_RADIUS_SCALE_DP,
    DEFAULT_SPACING_SCALE_DP,
    check_compose,
)


def _findings_by_check(source: str, check: str) -> list:
    report = check_compose(source, path="Test.kt")
    return [f for f in report.findings if f.check == check]


# ============================================================================
# Trivial inputs
# ============================================================================


def test_empty_source_yields_no_findings() -> None:
    report = check_compose("", path="Empty.kt")
    assert report.findings == ()
    assert report.language == "kotlin"
    assert report.file == "Empty.kt"


def test_file_without_compose_yields_no_findings() -> None:
    source = """
    package foo.bar

    fun add(a: Int, b: Int): Int = a + b
    """
    report = check_compose(source)
    assert report.findings == ()


# ============================================================================
# Check 1 — undersized_tap_target  (a11y)
# ============================================================================


def test_undersized_size_modifier_is_flagged() -> None:
    source = """
    @Composable
    fun CloseIcon() {
        IconButton(onClick = {}, modifier = Modifier.size(32.dp)) { }
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1
    assert findings[0].category == "a11y"
    assert findings[0].severity == "high"
    assert findings[0].metric["value_dp"] == 32.0
    assert findings[0].metric["minimum_dp"] == 48.0


def test_at_minimum_size_is_not_flagged() -> None:
    source = """
    @Composable
    fun OkIcon() {
        IconButton(onClick = {}, modifier = Modifier.size(48.dp)) { }
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_token_size_reference_is_not_flagged() -> None:
    # Token reference — we cannot resolve the runtime value, so by the
    # honesty rule we MUST NOT flag it.
    source = """
    @Composable
    fun ThemedIcon() {
        IconButton(
            onClick = {},
            modifier = Modifier.size(MaterialTheme.dimensions.icon)
        ) { }
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_decorative_icon_size_is_not_flagged() -> None:
    # 0.0.9: a small Icon with no interactive ancestor is decorative, not
    # an undersized tap target. The Material spec says 48dp applies to
    # *touch targets*, not to icons in general.
    source = """
    @Composable
    fun DecorativeBadge() {
        Icon(
            imageVector = Icons.Filled.Info,
            contentDescription = null,
            modifier = Modifier.size(24.dp),
        )
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_decorative_image_size_is_not_flagged() -> None:
    source = """
    @Composable
    fun BrandLogo() {
        Image(
            painter = painterResource(R.drawable.logo),
            contentDescription = null,
            modifier = Modifier.size(32.dp),
        )
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_decorative_box_size_is_not_flagged() -> None:
    source = """
    @Composable
    fun Dot() {
        Box(modifier = Modifier.size(8.dp).background(Color.Red))
    }
    """
    assert _findings_by_check(source, "undersized_tap_target") == []


def test_clickable_modifier_chain_is_flagged() -> None:
    # `.clickable {}` turns ANY composable interactive — Box at 32dp with
    # a click handler is a real undersized tap target.
    source = """
    @Composable
    fun ClickableDot() {
        Box(modifier = Modifier.size(32.dp).clickable { /* go */ })
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1
    assert findings[0].metric["value_dp"] == 32.0


def test_toggleable_modifier_chain_is_flagged() -> None:
    source = """
    @Composable
    fun ToggleableDot() {
        Box(modifier = Modifier.size(40.dp).toggleable(value = true, onValueChange = {}))
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1


def test_selectable_modifier_chain_is_flagged() -> None:
    source = """
    @Composable
    fun SelectableDot() {
        Box(modifier = Modifier.size(36.dp).selectable(selected = false, onClick = {}))
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1


def test_chip_size_is_flagged() -> None:
    # Chip is interactive in Material — must enforce 48dp.
    source = """
    @Composable
    fun TinyChip() {
        FilterChip(
            selected = false,
            onClick = {},
            label = { Text("x") },
            modifier = Modifier.size(40.dp),
        )
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1


def test_snippet_is_short_and_single_line() -> None:
    # 0.0.9: snippets used to be `_node_text(call_expression)` which on
    # chained Modifier calls returned the whole receiver chain. Now the
    # finding's snippet is just `.padding(13.dp)` — short, one line, no
    # surrounding context.
    source = """
    @Composable
    fun Card() {
        Column(modifier = Modifier.padding(13.dp)) { }
    }
    """
    findings = _findings_by_check(source, "off_scale_spacing")
    assert len(findings) == 1
    snippet = findings[0].snippet
    assert snippet == ".padding(13.dp)"
    assert "\n" not in snippet


def test_undersized_tap_target_snippet_is_short() -> None:
    source = """
    @Composable
    fun X() {
        IconButton(onClick = {}, modifier = Modifier.size(32.dp)) { }
    }
    """
    findings = _findings_by_check(source, "undersized_tap_target")
    assert len(findings) == 1
    snippet = findings[0].snippet
    # Just the offending modifier, no `IconButton(...)` wrapper.
    assert snippet == ".size(32.dp)"
    assert "IconButton" not in snippet


# ============================================================================
# Check 2 — off_scale_spacing  (consistency)
# ============================================================================


def test_off_scale_padding_is_flagged() -> None:
    source = """
    @Composable
    fun Box() {
        Column(modifier = Modifier.padding(13.dp)) { }
    }
    """
    findings = _findings_by_check(source, "off_scale_spacing")
    assert len(findings) == 1
    assert findings[0].category == "consistency"
    assert findings[0].metric["value_dp"] == 13.0


def test_on_scale_padding_is_not_flagged() -> None:
    source = """
    @Composable
    fun Box() {
        Column(modifier = Modifier.padding(16.dp)) { }
    }
    """
    assert _findings_by_check(source, "off_scale_spacing") == []


def test_named_arg_padding_is_skipped_in_v1() -> None:
    # Named args like `padding(horizontal = 8.dp)` are intentionally not
    # checked in v1 — we only flag the single-literal shape. Documented
    # honestly in the SKILL and the core module.
    source = """
    @Composable
    fun Box() {
        Column(modifier = Modifier.padding(horizontal = 7.dp, vertical = 9.dp)) { }
    }
    """
    assert _findings_by_check(source, "off_scale_spacing") == []


def test_custom_spacing_scale_changes_findings() -> None:
    source = """
    @Composable
    fun Box() {
        Column(modifier = Modifier.padding(13.dp)) { }
    }
    """
    # 13 IS on this custom scale, so it must not flag.
    report = check_compose(source, spacing_scale=(0, 13, 26))
    off_scale = [f for f in report.findings if f.check == "off_scale_spacing"]
    assert off_scale == []


# ============================================================================
# Check 3 — hardcoded_color  (token)
# ============================================================================


def test_hardcoded_argb_color_is_flagged() -> None:
    source = """
    @Composable
    fun Brand() {
        Surface(color = Color(0xFF3B82F6)) { }
    }
    """
    findings = _findings_by_check(source, "hardcoded_color")
    assert len(findings) == 1
    assert findings[0].category == "token"
    assert findings[0].metric["hex"] == "#3B82F6"


def test_hardcoded_rgb_color_is_flagged() -> None:
    # 6-digit hex (no alpha) — also a literal, must flag.
    source = """
    @Composable
    fun Brand() {
        Surface(color = Color(0x3B82F6)) { }
    }
    """
    findings = _findings_by_check(source, "hardcoded_color")
    assert len(findings) == 1
    assert findings[0].metric["hex"] == "#3B82F6"


def test_theme_color_reference_is_not_flagged() -> None:
    source = """
    @Composable
    fun Themed() {
        Surface(color = MaterialTheme.colorScheme.primary) { }
    }
    """
    assert _findings_by_check(source, "hardcoded_color") == []


def test_named_color_constant_is_not_flagged() -> None:
    # `Color.Red` is a named constant. We can't infer its hex statically,
    # and conventionally these are deliberate. Don't flag.
    source = """
    @Composable
    fun Themed() {
        Surface(color = Color.Red) { }
    }
    """
    assert _findings_by_check(source, "hardcoded_color") == []


def test_color_literal_in_lightColorScheme_is_not_flagged() -> None:
    # 0.0.9 honesty rule: literals inside a colour-palette factory are
    # the design system's OWN definition, not a hardcoded consumer.
    source = """
    val LightPalette = lightColorScheme(
        primary = Color(0xFF3B82F6),
        onPrimary = Color(0xFFFFFFFF),
        surface = Color(0xFFFAFAFA),
    )
    """
    assert _findings_by_check(source, "hardcoded_color") == []


def test_color_literal_in_darkColorScheme_is_not_flagged() -> None:
    source = """
    val DarkPalette = darkColorScheme(
        primary = Color(0xFF60A5FA),
        onPrimary = Color(0xFF000000),
    )
    """
    assert _findings_by_check(source, "hardcoded_color") == []


def test_color_literal_in_colors_kt_file_is_not_flagged() -> None:
    # Same literals, same callsite shape — but the *filename* says this is
    # the colour layer. Common pattern: top-level `val Primary500 = Color(...)`.
    source = """
    val Primary500 = Color(0xFF3B82F6)
    val Surface100 = Color(0xFFFAFAFA)
    """
    report = check_compose(source, path="ui/theme/Colors.kt")
    assert [f for f in report.findings if f.check == "hardcoded_color"] == []


def test_color_literal_in_palette_kt_file_is_not_flagged() -> None:
    source = "val Brand = Color(0xFF3B82F6)"
    report = check_compose(source, path="ui/theme/AppPalette.kt")
    assert [f for f in report.findings if f.check == "hardcoded_color"] == []


def test_color_literal_in_theme_kt_file_is_still_flagged() -> None:
    # Theme.kt usually *consumes* tokens — hardcoded literals there ARE
    # a real finding. Honesty rule deliberately doesn't whitelist this file.
    source = """
    @Composable
    fun MyTheme(content: @Composable () -> Unit) {
        Surface(color = Color(0xFF3B82F6)) { content() }
    }
    """
    report = check_compose(source, path="ui/theme/Theme.kt")
    assert len([f for f in report.findings if f.check == "hardcoded_color"]) == 1


def test_color_literal_in_consumer_file_is_still_flagged() -> None:
    # Sanity: the new whitelist must NOT silence consumer hardcoded colours.
    source = """
    @Composable
    fun LoginButton() {
        Button(colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF3B82F6))) { }
    }
    """
    report = check_compose(source, path="feature/login/LoginButton.kt")
    findings = [f for f in report.findings if f.check == "hardcoded_color"]
    assert len(findings) == 1


# ============================================================================
# Check 4 — off_scale_radius  (consistency)
# ============================================================================


def test_off_scale_radius_is_flagged() -> None:
    source = """
    @Composable
    fun Card() {
        Surface(shape = RoundedCornerShape(13.dp)) { }
    }
    """
    findings = _findings_by_check(source, "off_scale_radius")
    assert len(findings) == 1
    assert findings[0].category == "consistency"
    assert findings[0].metric["value_dp"] == 13.0


def test_on_scale_radius_is_not_flagged() -> None:
    source = """
    @Composable
    fun Card() {
        Surface(shape = RoundedCornerShape(12.dp)) { }
    }
    """
    assert _findings_by_check(source, "off_scale_radius") == []


def test_per_corner_radius_is_skipped_in_v1() -> None:
    # Named per-corner radii (`RoundedCornerShape(topStart = 16.dp, ...)`)
    # are intentionally not checked in v1.
    source = """
    @Composable
    fun Card() {
        Surface(shape = RoundedCornerShape(topStart = 13.dp, topEnd = 13.dp)) { }
    }
    """
    assert _findings_by_check(source, "off_scale_radius") == []


def test_token_radius_reference_is_not_flagged() -> None:
    source = """
    @Composable
    fun Card() {
        Surface(shape = RoundedCornerShape(MaterialTheme.dimensions.radiusMd)) { }
    }
    """
    assert _findings_by_check(source, "off_scale_radius") == []


# ============================================================================
# Report aggregation
# ============================================================================


def test_findings_are_sorted_by_severity_then_location() -> None:
    # 1 high (undersized), 1 medium (color), 1 low (radius).
    source = """
    @Composable
    fun All() {
        IconButton(onClick = {}, modifier = Modifier.size(20.dp)) { }
        Surface(color = Color(0xFFAA0000)) { }
        Surface(shape = RoundedCornerShape(13.dp)) { }
    }
    """
    report = check_compose(source)
    severities = [f.severity for f in report.findings]
    assert severities == sorted(
        severities,
        key=lambda s: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[s],
    )
    # All three checks fired.
    checks = {f.check for f in report.findings}
    assert "undersized_tap_target" in checks
    assert "hardcoded_color" in checks
    assert "off_scale_radius" in checks


def test_counts_by_severity_and_category_are_consistent() -> None:
    source = """
    @Composable
    fun All() {
        IconButton(onClick = {}, modifier = Modifier.size(20.dp)) { }
        Surface(color = Color(0xFFAA0000)) { }
    }
    """
    report = check_compose(source)
    assert sum(report.counts_by_severity.values()) == len(report.findings)
    assert sum(report.counts_by_category.values()) == len(report.findings)


def test_default_scales_are_immutable_tuples() -> None:
    # Sanity: the defaults are tuples (frozen), not lists. Prevents accidental
    # mutation across check_compose() calls.
    assert isinstance(DEFAULT_SPACING_SCALE_DP, tuple)
    assert isinstance(DEFAULT_RADIUS_SCALE_DP, tuple)
