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
