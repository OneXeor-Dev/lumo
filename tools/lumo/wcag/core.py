"""W3C luminance + contrast math and OKLCH auto-correct.

References:
  - WCAG 2.2 Relative Luminance: https://www.w3.org/WAI/GL/wiki/Relative_luminance
  - WCAG 2.2 Contrast (Minimum) 1.4.3 — AA: 4.5:1 normal, 3:1 large
  - WCAG 2.2 Contrast (Enhanced) 1.4.6 — AAA: 7:1 normal, 4.5:1 large
  - OKLCH: https://bottosson.github.io/posts/oklab/
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Level = Literal["AA", "AAA"]
Size = Literal["normal", "large"]


# ============================================================================
# Color parsing
# ============================================================================


def _parse_hex(color: str) -> tuple[int, int, int]:
    """Parse #RGB, #RRGGBB, #RGBA, #RRGGBBAA. Alpha channel is dropped.

    Raises ValueError on malformed input.
    """
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    elif len(c) == 4:
        c = "".join(ch * 2 for ch in c[:3])
    elif len(c) == 8:
        c = c[:6]
    if len(c) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in c):
        raise ValueError(f"Invalid hex color: {color!r}")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _to_hex(r: int, g: int, b: int) -> str:
    """Format an (r, g, b) triple back to #RRGGBB (uppercase)."""
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b)),
    )


# ============================================================================
# WCAG luminance + contrast
# ============================================================================


def _srgb_to_linear(channel_8bit: int) -> float:
    """sRGB gamma → linear-light. Per WCAG 2.2 spec."""
    c = channel_8bit / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """W3C relative luminance L in [0, 1]. Higher = lighter.

    Formula: 0.2126·R + 0.7152·G + 0.0722·B (linear-light channels).
    """
    r, g, b = _parse_hex(color)
    rl = _srgb_to_linear(r)
    gl = _srgb_to_linear(g)
    bl = _srgb_to_linear(b)
    return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio in [1.0, 21.0]. Order-independent."""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


_THRESHOLDS: dict[tuple[Level, Size], float] = {
    ("AA", "normal"): 4.5,
    ("AA", "large"): 3.0,
    ("AAA", "normal"): 7.0,
    ("AAA", "large"): 4.5,
}


def required_ratio(level: Level, size: Size) -> float:
    """Required WCAG ratio for (level, size). Raises KeyError on invalid combo."""
    return _THRESHOLDS[(level, size)]


@dataclass(frozen=True)
class CheckResult:
    fg: str
    bg: str
    ratio: float
    level: Level
    size: Size
    required: float
    passes: bool


def check_pair(
    fg: str,
    bg: str,
    level: Level = "AA",
    size: Size = "normal",
) -> CheckResult:
    """Check if (fg, bg) meets WCAG (level, size). Returns a CheckResult."""
    ratio = contrast_ratio(fg, bg)
    required = required_ratio(level, size)
    return CheckResult(
        fg=fg.upper() if fg.startswith("#") else fg,
        bg=bg.upper() if bg.startswith("#") else bg,
        ratio=round(ratio, 3),
        level=level,
        size=size,
        required=required,
        passes=ratio >= required,
    )


# ============================================================================
# OKLCH conversion (sRGB ↔ OKLab ↔ OKLCH)
#
# Source: Björn Ottosson, https://bottosson.github.io/posts/oklab/
# OKLab is a perceptual color space — lightness changes feel uniform to the eye.
# OKLCH = polar form of OKLab: (Lightness, Chroma, Hue).
# Adjusting L while keeping C and H gives a perceptually-natural lighten/darken.
# ============================================================================


def _srgb_to_oklab(r: int, g: int, b: int) -> tuple[float, float, float]:
    rl, gl, bl = (_srgb_to_linear(ch) for ch in (r, g, b))

    l = 0.4122214708 * rl + 0.5363325363 * gl + 0.0514459929 * bl
    m = 0.2119034982 * rl + 0.6806995451 * gl + 0.1073969566 * bl
    s = 0.0883024619 * rl + 0.2817188376 * gl + 0.6299787005 * bl

    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))

    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab_to_linear_srgb(L: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3

    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _linear_to_srgb_byte(c: float) -> int:
    c = max(0.0, min(1.0, c))
    srgb = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return round(srgb * 255)


def _hex_to_oklch(color: str) -> tuple[float, float, float]:
    r, g, b = _parse_hex(color)
    L, A, B = _srgb_to_oklab(r, g, b)
    C = math.sqrt(A * A + B * B)
    H = math.atan2(B, A)
    return L, C, H


def _oklch_to_hex(L: float, C: float, H: float) -> str:
    a = C * math.cos(H)
    b = C * math.sin(H)
    rl, gl, bl = _oklab_to_linear_srgb(L, a, b)
    return _to_hex(_linear_to_srgb_byte(rl), _linear_to_srgb_byte(gl), _linear_to_srgb_byte(bl))


# ============================================================================
# Auto-correct
# ============================================================================


@dataclass(frozen=True)
class CorrectionResult:
    """Outcome of `auto_correct`.

    If `corrected_fg == fg` and `original.passes` is True, nothing was changed.
    `iterations` is informational — useful for tests and for showing the user
    that the algorithm is deterministic and bounded.
    """

    original: CheckResult
    corrected_fg: str
    corrected_bg: str
    corrected: CheckResult
    iterations: int
    strategy: Literal["unchanged", "darken_fg", "lighten_fg"]


def auto_correct(
    fg: str,
    bg: str,
    level: Level = "AA",
    size: Size = "normal",
    max_iterations: int = 60,
) -> CorrectionResult:
    """Iteratively adjust the foreground L-channel in OKLCH until the pair passes.

    Strategy:
      - If the original passes, return unchanged.
      - Otherwise pick a direction:
          * If fg is darker than bg, push fg darker (decrease L).
          * Else push fg lighter (increase L).
      - Step L by ±0.02 (perceptually-uniform — a small but visible step) up to
        `max_iterations`. If we never reach the threshold (e.g. bg is mid-gray
        and direction was wrong by coincidence), fall back to the opposite
        direction once.

    Chroma and Hue are preserved, so brand identity stays intact.
    """
    original = check_pair(fg, bg, level, size)
    if original.passes:
        return CorrectionResult(
            original=original,
            corrected_fg=original.fg,
            corrected_bg=original.bg,
            corrected=original,
            iterations=0,
            strategy="unchanged",
        )

    L_fg, C_fg, H_fg = _hex_to_oklch(fg)
    L_bg = _hex_to_oklch(bg)[0]
    direction: Literal["darken_fg", "lighten_fg"] = (
        "darken_fg" if L_fg < L_bg else "lighten_fg"
    )
    step = -0.02 if direction == "darken_fg" else 0.02

    def _try_direction(start_L: float, signed_step: float) -> tuple[str, CheckResult, int]:
        L = start_L
        for i in range(1, max_iterations + 1):
            L = max(0.0, min(1.0, L + signed_step))
            candidate = _oklch_to_hex(L, C_fg, H_fg)
            result = check_pair(candidate, bg, level, size)
            if result.passes:
                return candidate, result, i
            if L <= 0.0 or L >= 1.0:
                break
        return _oklch_to_hex(L, C_fg, H_fg), check_pair(
            _oklch_to_hex(L, C_fg, H_fg), bg, level, size
        ), max_iterations

    candidate_hex, candidate_check, iters = _try_direction(L_fg, step)
    if not candidate_check.passes:
        candidate_hex, candidate_check, iters2 = _try_direction(L_fg, -step)
        iters += iters2
        direction = "lighten_fg" if direction == "darken_fg" else "darken_fg"

    return CorrectionResult(
        original=original,
        corrected_fg=candidate_hex,
        corrected_bg=original.bg,
        corrected=candidate_check,
        iterations=iters,
        strategy=direction,
    )
