"""Overlay lumo-theory findings on a Figma frame PNG.

Optional feature — requires `pillow` (`pip install lumo-mobile[viz]`).
The dependency stays optional because the core render / diff / theory
pipeline is pure Python, and we don't want to drag Pillow into every
install just for visualisation.

Usage shape:
    findings = json.load(open("findings.json"))    # lumo-theory --json
    layout   = json.load(open("layout.json"))      # lumo-figma render --json
    annotate_png(
        png_in="frame.png",
        layout=layout,
        findings=findings,
        png_out="annotated.png",
        severities=("high",),       # default — only HIGH gets drawn
    )

The output is a PNG with translucent red boxes + numbered badges over
every flagged element. Element bboxes come from `layout["elements"]`;
findings reference elements by id via `finding["elements"][0]`.

The PNG is assumed to be a `--scale 2` Figma export — layout
coordinates are multiplied by 2 to match. Override `scale` if you
exported at a different scale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_SCALE = 2.0
DEFAULT_SEVERITIES = ("high",)

# Severity → (border colour, fill colour). Translucent fill so the
# underlying Figma frame remains readable.
_SEVERITY_COLOURS: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "critical": ((180, 0, 0, 255), (180, 0, 0, 100)),
    "high":     ((255, 60, 60, 255), (255, 60, 60, 80)),
    "medium":   ((255, 140, 0, 220), (255, 140, 0, 60)),
    "low":      ((255, 200, 0, 200), (255, 200, 0, 50)),
    "info":     ((0, 120, 200, 200), (0, 120, 200, 50)),
}


def annotate_png(
    *,
    png_in: str | Path,
    layout: Mapping[str, Any],
    findings: Iterable[Mapping[str, Any]],
    png_out: str | Path,
    scale: float = DEFAULT_SCALE,
    severities: Iterable[str] = DEFAULT_SEVERITIES,
) -> Path:
    """Write an annotated PNG with finding boxes drawn over `png_in`.

    Args:
        png_in: Source PNG (typically Figma export at `scale`).
        layout: Lumo layout JSON — needs `elements[].id/x/y/w/h`.
        findings: Lumo theory findings — each `finding["elements"][0]`
                  is the id we draw a box around.
        png_out: Destination PNG path.
        scale: Multiplier from layout coords to PNG pixels. Default 2
               because lumo-figma render exports at scale=2.
        severities: Which severities to draw. Default ("high",) — the
                    real signal. Pass e.g. ("high", "medium") to widen.

    Returns:
        Resolved `png_out` Path.

    Raises:
        ImportError: if Pillow isn't installed — surfaces the install
                     hint rather than a cryptic ModuleNotFoundError.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover — env-dependent
        raise ImportError(
            "lumo-figma annotate requires Pillow. Install with:\n"
            "  pip install 'lumo-mobile[viz]'\n"
            "or directly:\n"
            "  pip install pillow"
        ) from exc

    sev_set = set(severities)
    by_id = {e["id"]: e for e in layout.get("elements", [])}

    # Filter + dedupe findings by primary element. One element can have
    # multiple findings; we draw one box per element with all messages
    # collected into a single label.
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for f in findings:
        if f.get("severity") not in sev_set:
            continue
        els = f.get("elements") or []
        if not els:
            continue
        primary = els[0]
        grouped.setdefault(primary, []).append(f)

    im = Image.open(str(png_in)).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Best-effort font lookup. Fall back to default if neither is found.
    font = _load_font(28)
    label_font = _load_font(22)

    for idx, (eid, finding_list) in enumerate(grouped.items(), 1):
        el = by_id.get(eid)
        if el is None or el.get("x") is None:
            continue
        x = float(el["x"]) * scale
        y = float(el["y"]) * scale
        w = float(el["w"]) * scale
        h = float(el["h"]) * scale

        # Pick the most severe colour across this element's findings.
        worst = _worst_severity(f.get("severity", "info") for f in finding_list)
        border, fill = _SEVERITY_COLOURS.get(worst, _SEVERITY_COLOURS["high"])

        draw.rectangle([x, y, x + w, y + h], fill=fill, outline=border, width=5)

        # Badge — numbered, top-left, anchored just above the bbox.
        badge_size = 44
        badge_y = max(0, y - badge_size - 2)
        draw.rectangle(
            [x - 2, badge_y, x + badge_size, badge_y + badge_size],
            fill=border, outline=border,
        )
        draw.text((x + 12, badge_y + 4), str(idx), fill=(255, 255, 255, 255), font=font)

        # Label — first finding's check + short message, right of bbox.
        primary_check = finding_list[0].get("check", "?")
        label_text = f"#{idx} {primary_check}"
        if len(finding_list) > 1:
            label_text += f" (+{len(finding_list) - 1})"
        draw.text((x + w + 8, y + 4), label_text, fill=border, font=label_font)

    out = Image.alpha_composite(im, overlay)
    out_path = Path(png_out)
    out.convert("RGB").save(out_path, "PNG")
    return out_path


def _load_font(size: int) -> Any:
    """Try common font paths; fall back to Pillow's default bitmap font."""
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",   # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",   # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",   # Windows
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


_SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


def _worst_severity(severities: Iterable[str]) -> str:
    """Return the most-severe label from an iterable; default 'info'."""
    worst = "info"
    worst_rank = 0
    for s in severities:
        rank = _SEVERITY_RANK.get(s, 0)
        if rank > worst_rank:
            worst = s
            worst_rank = rank
    return worst
