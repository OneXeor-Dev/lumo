"""Validators for lumo-spec.

Three guards, all pure Python and applied after the LLM call:

1. Length cap — fail fast, NEVER silent-truncate (honesty rule 7).
2. Schema validation — coerce raw LLM dicts into typed `Finding`s, dropping
   any that violate the locked enums.
3. Evidence-substring — reject any finding whose `evidence` quote is not a
   verbatim substring of the fetched spec text (honesty rule 3). This is the
   belt-and-suspenders guard against quote fabrication.
"""

from __future__ import annotations

import sys
from typing import Any

from lumo.spec.models import CONFIDENCES, FINDING_IDS, SEVERITIES, Finding

# Phase 1 conservative placeholder. The final cap is derived from the chosen
# model's context window minus an output buffer and the real length
# distribution of Plazo specs, measured during dogfood (Phase 5). Documented as
# a placeholder so it is not mistaken for a measured value.
SPEC_CHAR_CAP = 32_000


class SpecTooLongError(ValueError):
    """Raised when the flattened spec exceeds the hard cap."""


def enforce_length_cap(markdown: str, cap: int = SPEC_CHAR_CAP) -> None:
    """Fail fast if the spec is over the cap. Never truncate silently."""
    n = len(markdown)
    if n > cap:
        raise SpecTooLongError(
            f"spec is {n:,} characters, over the {cap:,} cap. "
            "The spec was NOT truncated and NOT checked. Workarounds: split the "
            "page into smaller specs, pass the parent page/ticket only, or (Phase 3) "
            "raise the cap via env once that is supported."
        )


def coerce_findings(raw: list[dict[str, Any]]) -> tuple[list[Finding], int]:
    """Turn raw LLM dicts into typed Findings.

    Returns (findings, dropped). A finding is dropped (counted, warned on
    stderr) when it violates a locked enum or is missing a required field —
    the structured-output schema should prevent this, but we defend in depth.
    """
    out: list[Finding] = []
    dropped = 0
    for item in raw:
        if not _valid_enums(item):
            dropped += 1
            print(
                f"finding dropped: schema violation ({item.get('id')!r}/"
                f"{item.get('severity')!r}/{item.get('confidence')!r})",
                file=sys.stderr,
            )
            continue
        try:
            out.append(
                Finding(
                    id=item["id"],
                    severity=item["severity"],
                    confidence=item["confidence"],
                    message=str(item["message"]),
                    evidence=str(item["evidence"]),
                    recommendation=str(item["recommendation"]),
                    element=item.get("element"),
                )
            )
        except KeyError as exc:
            dropped += 1
            print(f"finding dropped: missing field {exc}", file=sys.stderr)
    return out, dropped


def _valid_enums(item: dict[str, Any]) -> bool:
    return (
        item.get("id") in FINDING_IDS
        and item.get("severity") in SEVERITIES
        and item.get("confidence") in CONFIDENCES
    )


def validate_evidence(
    findings: list[Finding], spec_markdown: str
) -> tuple[list[Finding], int]:
    """Drop findings whose evidence is not a verbatim substring of the spec.

    Returns (kept, dropped). Dropped findings warn on stderr so users see when
    the fabrication guard fires. Whitespace is normalised on both sides before
    the substring check so a quote that differs only in run-of-spaces / newline
    wrapping is not falsely rejected — but the quote must still be present.
    """
    spec_norm = _normalise_ws(spec_markdown)
    kept: list[Finding] = []
    dropped = 0
    for f in findings:
        quote = f.evidence.strip()
        if quote and _normalise_ws(quote) in spec_norm:
            kept.append(f)
        else:
            dropped += 1
            preview = quote[:60] + ("…" if len(quote) > 60 else "")
            print(
                f"finding dropped: fabricated evidence (not found in spec): "
                f'"{preview}"',
                file=sys.stderr,
            )
    return kept, dropped


def _normalise_ws(text: str) -> str:
    return " ".join(text.split())
