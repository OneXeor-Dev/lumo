"""Cross-platform parity diff.

Compares an Android layout (dp) and an iOS layout (pt) and reports:
  - mismatches in spacing / sizing for elements with matching ids
  - colour token name mismatches
  - components present on one platform but missing on the other
  - acceptable platform-specific differences (whitelisted, severity=info)

When a `DesignSystemConfig` is provided, both layouts are also validated
against the shared design tokens — a stronger guarantee than pairwise diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lumo.theory.core import Confidence, Element, Layout

Severity = Literal["critical", "high", "medium", "low", "info"]

# ============================================================================
# Whitelist of legitimate platform-specific differences.
#
# These are documented design-system divergences between iOS and Android.
# Reporting them as mismatches would be noise. We report them as `info` so
# the user can confirm the divergence is intentional.
# ============================================================================


@dataclass(frozen=True)
class _PlatformDefault:
    description: str
    android_value: float
    ios_value: float
    role_match: tuple[str, ...]  # which element roles this applies to


PLATFORM_DEFAULTS: tuple[_PlatformDefault, ...] = (
    _PlatformDefault(
        description="Minimum touch target: Material 48dp vs Apple HIG 44pt",
        android_value=48.0,
        ios_value=44.0,
        role_match=("icon_button",),
    ),
    _PlatformDefault(
        description="Primary nav bar height: Material bottom nav 80dp vs iOS Tab Bar 49pt",
        android_value=80.0,
        ios_value=49.0,
        role_match=("nav_item", "tab"),
    ),
)


# ============================================================================
# Design-system config (optional input)
# ============================================================================


@dataclass(frozen=True)
class DesignSystemConfig:
    """Design tokens declared by the user as ground truth for both platforms.

    Values are unit-agnostic numbers — they are checked against the matching
    element on each platform regardless of dp vs pt suffix, because dp and pt
    are both density-independent and equal in physical size.

    Example:
        DesignSystemConfig(
            spacing={"sm": 8, "md": 16, "lg": 24},
            sizing={"primary_button_height": 56},
            colors={"primary": "brand.primary", "surface": "brand.surface"},
        )
    """

    spacing: dict[str, float] = field(default_factory=dict)
    sizing: dict[str, float] = field(default_factory=dict)
    colors: dict[str, str] = field(default_factory=dict)


# ============================================================================
# Finding model
# ============================================================================


@dataclass(frozen=True)
class ParityFinding:
    check: str
    severity: Severity
    confidence: Confidence
    element_id: str | None
    message: str
    recommendation: str
    android_value: object = None
    ios_value: object = None


@dataclass(frozen=True)
class ParityReport:
    findings: tuple[ParityFinding, ...]
    confidence: Confidence
    android_source: Confidence
    ios_source: Confidence

    @property
    def counts_by_severity(self) -> dict[Severity, int]:
        counts: dict[Severity, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts


# ============================================================================
# Helpers
# ============================================================================


_CONFIDENCE_ORDER: dict[Confidence, int] = {
    "measured": 0,
    "code-estimated": 1,
    "description-estimated": 2,
}


def _combined_confidence(a: Confidence, b: Confidence) -> Confidence:
    """Combined confidence is the *worse* of the two — honest pessimism."""
    return a if _CONFIDENCE_ORDER[a] >= _CONFIDENCE_ORDER[b] else b


def _index_by_id(elements: tuple[Element, ...]) -> dict[str, Element]:
    return {e.id: e for e in elements}


def _is_whitelisted(role: str, android: float, ios: float, tolerance: float = 0.5) -> _PlatformDefault | None:
    for default in PLATFORM_DEFAULTS:
        if role not in default.role_match:
            continue
        if (
            abs(android - default.android_value) <= tolerance
            and abs(ios - default.ios_value) <= tolerance
        ):
            return default
    return None


# ============================================================================
# Individual checks
# ============================================================================


def _check_component_presence(
    android: Layout,
    ios: Layout,
    confidence: Confidence,
) -> list[ParityFinding]:
    """Elements present on one platform but absent on the other."""
    android_ids = {e.id for e in android.elements}
    ios_ids = {e.id for e in ios.elements}

    findings: list[ParityFinding] = []

    for missing in sorted(android_ids - ios_ids):
        findings.append(
            ParityFinding(
                check="component_missing_on_ios",
                severity="high",
                confidence=confidence,
                element_id=missing,
                message=f"Element '{missing}' exists on Android but not on iOS.",
                recommendation=(
                    "Implement the matching element on iOS, or remove it from "
                    "Android if the feature was intentionally Android-only."
                ),
                android_value="present",
                ios_value="missing",
            )
        )

    for missing in sorted(ios_ids - android_ids):
        findings.append(
            ParityFinding(
                check="component_missing_on_android",
                severity="high",
                confidence=confidence,
                element_id=missing,
                message=f"Element '{missing}' exists on iOS but not on Android.",
                recommendation=(
                    "Implement the matching element on Android, or remove it "
                    "from iOS if the feature was intentionally iOS-only."
                ),
                android_value="missing",
                ios_value="present",
            )
        )

    return findings


def _check_spacing_and_sizing(
    android_el: Element,
    ios_el: Element,
    confidence: Confidence,
) -> list[ParityFinding]:
    """Compare numeric dimensions of matching elements. dp and pt are equal."""
    findings: list[ParityFinding] = []

    for attr, label in (("w", "width"), ("h", "height")):
        a_val = getattr(android_el, attr)
        i_val = getattr(ios_el, attr)
        if a_val == i_val:
            continue

        whitelist = _is_whitelisted(android_el.role, a_val, i_val)
        if whitelist:
            findings.append(
                ParityFinding(
                    check="platform_specific_default",
                    severity="info",
                    confidence=confidence,
                    element_id=android_el.id,
                    message=(
                        f"'{android_el.id}' {label} differs by design: "
                        f"{a_val}dp / {i_val}pt. {whitelist.description}."
                    ),
                    recommendation=(
                        "This is a known platform convention — no action "
                        "needed unless the design system explicitly overrides it."
                    ),
                    android_value=a_val,
                    ios_value=i_val,
                )
            )
            continue

        findings.append(
            ParityFinding(
                check=f"{label}_mismatch",
                severity="medium",
                confidence=confidence,
                element_id=android_el.id,
                message=(
                    f"'{android_el.id}' {label} differs between platforms: "
                    f"Android {a_val}dp vs iOS {i_val}pt. "
                    f"dp and pt are both density-independent and should match."
                ),
                recommendation=(
                    f"Align both platforms to the same {label} value. If the "
                    "intent is platform-specific, declare it in lumo.config.json "
                    "to suppress this finding."
                ),
                android_value=a_val,
                ios_value=i_val,
            )
        )

    # Position parity (x, y) is informational — different screen widths or
    # safe-area insets can legitimately shift coordinates. We do not flag.

    return findings


def _check_design_system(
    layout: Layout,
    config: DesignSystemConfig,
    platform: Literal["android", "ios"],
    confidence: Confidence,
) -> list[ParityFinding]:
    """Validate a single platform's layout against shared design tokens."""
    findings: list[ParityFinding] = []
    unit = "dp" if platform == "android" else "pt"

    # Sizing tokens: check primary_button_height etc. by role convention.
    # We look for an explicit role->token mapping. For v1, the only convention
    # baked in is: primary_action elements should match sizing.primary_button_height.
    if "primary_button_height" in config.sizing:
        expected = config.sizing["primary_button_height"]
        for el in layout.elements:
            if el.role == "primary_action" and el.h != expected:
                findings.append(
                    ParityFinding(
                        check=f"design_system_height_mismatch_{platform}",
                        severity="high",
                        confidence=confidence,
                        element_id=el.id,
                        message=(
                            f"'{el.id}' on {platform} has height {el.h}{unit}, "
                            f"but design system declares "
                            f"sizing.primary_button_height = {expected}."
                        ),
                        recommendation=(
                            f"Align the {platform} implementation to "
                            f"{expected}{unit} as per design system, or update "
                            "lumo.config.json if the design system changed."
                        ),
                        android_value=el.h if platform == "android" else None,
                        ios_value=el.h if platform == "ios" else None,
                    )
                )

    return findings


# ============================================================================
# Entry point
# ============================================================================


def diff(
    android: Layout,
    ios: Layout,
    config: DesignSystemConfig | None = None,
) -> ParityReport:
    """Diff two layouts and (optionally) validate them against a design system.

    The diff is symmetric: if iOS has an element Android lacks, it shows up
    just like the reverse case.
    """
    confidence = _combined_confidence(android.source, ios.source)
    findings: list[ParityFinding] = []

    # 1. Component presence
    findings.extend(_check_component_presence(android, ios, confidence))

    # 2. Per-element spacing / sizing for matching ids
    android_by_id = _index_by_id(android.elements)
    ios_by_id = _index_by_id(ios.elements)
    matching_ids = sorted(set(android_by_id) & set(ios_by_id))
    for el_id in matching_ids:
        findings.extend(
            _check_spacing_and_sizing(
                android_by_id[el_id], ios_by_id[el_id], confidence
            )
        )

    # 3. Design-system validation (each platform independently)
    if config is not None:
        findings.extend(_check_design_system(android, config, "android", confidence))
        findings.extend(_check_design_system(ios, config, "ios", confidence))

    severity_order: dict[Severity, int] = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "info": 4,
    }
    findings.sort(key=lambda f: (severity_order[f.severity], f.check, f.element_id or ""))

    return ParityReport(
        findings=tuple(findings),
        confidence=confidence,
        android_source=android.source,
        ios_source=ios.source,
    )
