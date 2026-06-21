"""Layout loading for lumo-spec.

Unlike `lumo-theory`, the spec check does not need pixel-accurate geometry —
it compares the *semantic content* of the layout (which elements exist, their
roles, labels, counts) against the spec text. So we keep the full element dicts
rather than dropping coordinate-less ones. The layout's own `source` label is
preserved verbatim and surfaced in the report; the spec check does not care how
the layout was produced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class LayoutError(ValueError):
    """Raised when a layout JSON is malformed for spec-check purposes."""


def load_layout(source: str) -> dict[str, Any]:
    """Load and minimally validate a Lumo layout JSON.

    `source == "-"` reads stdin. Returns the parsed dict unchanged (with a
    defaulted `source` field) so the LLM sees the full layout, including any
    fields newer tools attach.
    """
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - thin wrapper
        raise LayoutError(f"layout is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise LayoutError("layout JSON must be an object")
    if "elements" not in data or not isinstance(data["elements"], list):
        raise LayoutError("layout JSON must have an 'elements' array")

    data.setdefault("source", "description-estimated")
    return data


def layout_source(layout: dict[str, Any]) -> str:
    return str(layout.get("source", "description-estimated"))


def elements_count(layout: dict[str, Any]) -> int:
    return len(layout.get("elements", []))
