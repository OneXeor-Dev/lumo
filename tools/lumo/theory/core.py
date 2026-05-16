"""Cognitive-science layout checks for mobile UI.

Input is a structured layout description. The checks here are deliberately
conservative: every finding has a clear actionable recommendation, and every
metric is either device-independent or comes with explicit caveats.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["measured", "code-estimated", "description-estimated"]
Severity = Literal["critical", "high", "medium", "low", "info"]
Role = Literal[
    "primary_action",
    "secondary_action",
    "nav_item",
    "tab",
    "list_item",
    "input",
    "icon_button",
    "text",
    "image",
    "decorative",
]

# Min tap target per platform (Apple HIG 44pt, Material 48dp). Use the
# stricter of the two when the platform is unknown.
MIN_TAP_TARGET_DP = 48.0
MIN_TAP_TARGET_PT = 44.0

# Hick "comfort ceiling" for equally-weighted choices in a single navigation
# scope. Beyond this, decision time grows enough that visual hierarchy or
# grouping is required. 5 is Material's bottom-nav cap; we flag from 6.
HICK_EQUAL_WEIGHT_CEILING = 5

# Top corners on a phone are the hardest area to reach with one hand
# regardless of grip size. We flag primary actions that fall there.
TOP_CORNER_HEIGHT_FRACTION = 0.25  # top quarter of the screen
SIDE_CORNER_WIDTH_FRACTION = 0.25  # leftmost/rightmost quarter
PRIMARY_PREFERRED_BOTTOM_FRACTION = 0.5  # primary actions belong below midline


# ============================================================================
# Input data model
# ============================================================================


@dataclass(frozen=True)
class Screen:
    width: float
    height: float
    unit: Literal["dp", "pt"] = "dp"

    @property
    def min_tap_target(self) -> float:
        return MIN_TAP_TARGET_DP if self.unit == "dp" else MIN_TAP_TARGET_PT


@dataclass(frozen=True)
class Element:
    id: str
    role: Role
    x: float
    y: float
    w: float
    h: float
    group: str | None = None  # logical group for Gestalt proximity check
    weight: Literal["primary", "secondary", "equal"] = "equal"

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def smaller_side(self) -> float:
        return min(self.w, self.h)

    def is_interactive(self) -> bool:
        return self.role in {
            "primary_action",
            "secondary_action",
            "nav_item",
            "tab",
            "list_item",
            "input",
            "icon_button",
        }


@dataclass(frozen=True)
class Layout:
    screen: Screen
    elements: tuple[Element, ...]
    source: Confidence = "description-estimated"


# ============================================================================
# Output data model
# ============================================================================


@dataclass(frozen=True)
class Finding:
    check: str
    severity: Severity
    confidence: Confidence
    elements: tuple[str, ...]
    message: str
    recommendation: str
    metric: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportSummary:
    findings: tuple[Finding, ...]
    source: Confidence

    @property
    def counts_by_severity(self) -> dict[Severity, int]:
        counts: dict[Severity, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts


# ============================================================================
# Helpers
# ============================================================================


def _distance(a: Element, b: Element) -> float:
    return math.hypot(a.cx - b.cx, a.cy - b.cy)


def _fitts_index_of_difficulty(distance: float, target_smaller_side: float) -> float:
    """Shannon's Fitts ID = log2(D/W + 1). Dimensionless, device-independent.

    A higher ID means a harder-to-acquire target relative to others on the
    same screen. We never multiply by an unknown `b` constant — that's the
    part that produces shaky absolute times.
    """
    if target_smaller_side <= 0:
        return float("inf")
    return math.log2(distance / target_smaller_side + 1)


# ============================================================================
# Check 1 — Fitts difficulty (relative)
# ============================================================================


def _check_fitts(layout: Layout) -> list[Finding]:
    interactive = [e for e in layout.elements if e.is_interactive()]
    if len(interactive) < 2:
        return []

    # Use screen centre as the reference origin for movement distance — this is
    # the most defensible default for "first tap on entering screen". Future
    # versions can take a hand/origin parameter from the user.
    origin_x = layout.screen.width / 2
    origin_y = layout.screen.height / 2

    ids: list[tuple[Element, float]] = []
    for el in interactive:
        d = math.hypot(el.cx - origin_x, el.cy - origin_y)
        idx = _fitts_index_of_difficulty(d, el.smaller_side)
        ids.append((el, idx))

    if not ids:
        return []

    median_id = sorted(idx for _, idx in ids)[len(ids) // 2]
    findings: list[Finding] = []

    # Below tap-target minimum is critical regardless of Fitts ratio.
    min_target = layout.screen.min_tap_target
    for el, _idx in ids:
        if el.smaller_side < min_target:
            findings.append(
                Finding(
                    check="fitts_undersized_target",
                    severity="high",
                    confidence=layout.source,
                    elements=(el.id,),
                    message=(
                        f"Element '{el.id}' is {el.smaller_side:.0f}{layout.screen.unit} "
                        f"on its shorter side, below the minimum tap target "
                        f"({min_target:.0f}{layout.screen.unit})."
                    ),
                    recommendation=(
                        "Increase the touchable area to at least "
                        f"{min_target:.0f}{layout.screen.unit}, either by "
                        "growing the element or by extending the hit area "
                        "(Compose: Modifier.minimumInteractiveComponentSize; "
                        "SwiftUI: .contentShape; UIKit: hitTest override)."
                    ),
                    metric={"smaller_side": el.smaller_side, "minimum": min_target},
                )
            )

    # Relative Fitts difficulty: targets meaningfully harder than the median.
    # Threshold 1.4 ≈ a target that costs ~40% more movement-cost bits than
    # the median target on this screen.
    for el, idx in ids:
        if median_id > 0 and idx / median_id >= 1.4 and el.weight == "primary":
            findings.append(
                Finding(
                    check="fitts_difficult_primary",
                    severity="medium",
                    confidence=layout.source,
                    elements=(el.id,),
                    message=(
                        f"Primary action '{el.id}' has Fitts index of difficulty "
                        f"{idx:.2f}, while the median interactive target on this "
                        f"screen is {median_id:.2f} "
                        f"({idx / median_id:.2f}× harder)."
                    ),
                    recommendation=(
                        "Primary actions should be among the easiest-to-acquire "
                        "targets on the screen. Move it closer to the thumb-rest "
                        "area (bottom-centre on phones) or enlarge it."
                    ),
                    metric={"id_target": idx, "id_median": median_id},
                )
            )

    return findings


# ============================================================================
# Check 2 — Hick overload
# ============================================================================


def _check_hick(layout: Layout) -> list[Finding]:
    """Flag groups where many equally-weighted choices coexist without
    visual hierarchy. We only have signal here when elements share a `group`
    and all are marked weight='equal'.
    """
    groups: dict[str, list[Element]] = {}
    for el in layout.elements:
        if el.group and el.is_interactive() and el.weight == "equal":
            groups.setdefault(el.group, []).append(el)

    findings: list[Finding] = []
    for group_id, members in groups.items():
        n = len(members)
        if n > HICK_EQUAL_WEIGHT_CEILING:
            findings.append(
                Finding(
                    check="hick_overload",
                    severity="medium",
                    confidence=layout.source,
                    elements=tuple(m.id for m in members),
                    message=(
                        f"Group '{group_id}' has {n} equally-weighted choices. "
                        f"Hick's law: decision time grows logarithmically with "
                        f"choice count, and beyond {HICK_EQUAL_WEIGHT_CEILING} "
                        f"options users start to slow down or skim past."
                    ),
                    recommendation=(
                        "Reduce to ≤5, or introduce visual hierarchy "
                        "(primary action, grouping, progressive disclosure) so "
                        "the choices stop being weighted equally."
                    ),
                    metric={"n": n, "ceiling": HICK_EQUAL_WEIGHT_CEILING},
                )
            )
    return findings


# ============================================================================
# Check 3 — Gestalt proximity
# ============================================================================


def _check_gestalt_proximity(layout: Layout) -> list[Finding]:
    """For each pair of groups, the smallest distance between groups must be
    larger than the largest distance within either group. Otherwise the user
    cannot tell where one group ends and the next begins.
    """
    groups: dict[str, list[Element]] = {}
    for el in layout.elements:
        if el.group:
            groups.setdefault(el.group, []).append(el)

    findings: list[Finding] = []
    group_keys = [k for k, v in groups.items() if len(v) >= 2]

    for i, g1 in enumerate(group_keys):
        members1 = groups[g1]
        max_intra = max(_distance(a, b) for a in members1 for b in members1 if a.id != b.id)
        for g2 in group_keys[i + 1 :]:
            members2 = groups[g2]
            min_inter = min(_distance(a, b) for a in members1 for b in members2)
            if min_inter <= max_intra:
                findings.append(
                    Finding(
                        check="gestalt_proximity_violation",
                        severity="medium",
                        confidence=layout.source,
                        elements=tuple(m.id for m in members1 + members2),
                        message=(
                            f"Groups '{g1}' and '{g2}' fail Gestalt proximity: "
                            f"the closest elements between groups "
                            f"({min_inter:.0f}{layout.screen.unit}) are closer "
                            f"than the farthest elements within group '{g1}' "
                            f"({max_intra:.0f}{layout.screen.unit}). "
                            f"The eye will read them as one group."
                        ),
                        recommendation=(
                            "Increase the spacing between groups so the gap is "
                            "visibly larger than any internal gap, or merge the "
                            "groups if they belong together."
                        ),
                        metric={"min_inter": min_inter, "max_intra": max_intra},
                    )
                )
    return findings


# ============================================================================
# Check 4 — Reach (discrete rules, not a "law")
# ============================================================================


def _check_reach(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []
    sw = layout.screen.width
    sh = layout.screen.height
    top_corner_y = sh * TOP_CORNER_HEIGHT_FRACTION
    primary_min_y = sh * PRIMARY_PREFERRED_BOTTOM_FRACTION
    left_corner_x = sw * SIDE_CORNER_WIDTH_FRACTION
    right_corner_x = sw * (1 - SIDE_CORNER_WIDTH_FRACTION)

    for el in layout.elements:
        if el.weight != "primary" or not el.is_interactive():
            continue

        # Top corner = critical: hardest area to reach single-handed regardless
        # of grip size.
        in_top = el.cy <= top_corner_y
        in_corner_x = el.cx <= left_corner_x or el.cx >= right_corner_x
        if in_top and in_corner_x:
            findings.append(
                Finding(
                    check="reach_primary_in_top_corner",
                    severity="high",
                    confidence=layout.source,
                    elements=(el.id,),
                    message=(
                        f"Primary action '{el.id}' is in a top corner "
                        f"(x={el.cx:.0f}, y={el.cy:.0f}), the hardest area to "
                        f"reach one-handed on any modern phone size."
                    ),
                    recommendation=(
                        "Move primary actions into the bottom half of the "
                        "screen, ideally bottom-centre or within a bottom bar. "
                        "Top corners are acceptable for low-frequency actions "
                        "(close, settings, more)."
                    ),
                    metric={"x": el.cx, "y": el.cy},
                )
            )
            continue

        # Primary above mid-screen is a soft signal, not critical.
        if el.cy < primary_min_y:
            findings.append(
                Finding(
                    check="reach_primary_above_midline",
                    severity="low",
                    confidence=layout.source,
                    elements=(el.id,),
                    message=(
                        f"Primary action '{el.id}' sits above the screen "
                        f"midline (y={el.cy:.0f}, midline={primary_min_y:.0f})."
                    ),
                    recommendation=(
                        "On phones, primary actions are easier to reach in the "
                        "bottom half. Above the midline is fine for sparse "
                        "screens, but reconsider if the user will trigger this "
                        "action frequently."
                    ),
                    metric={"y": el.cy, "midline": primary_min_y},
                )
            )

    return findings


# ============================================================================
# Entry point
# ============================================================================


def check_layout(layout: Layout) -> ReportSummary:
    findings: list[Finding] = []
    findings.extend(_check_fitts(layout))
    findings.extend(_check_hick(layout))
    findings.extend(_check_gestalt_proximity(layout))
    findings.extend(_check_reach(layout))

    severity_order: dict[Severity, int] = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "info": 4,
    }
    findings.sort(key=lambda f: (severity_order[f.severity], f.check))

    return ReportSummary(findings=tuple(findings), source=layout.source)
