"""LLM call layer for lumo-spec.

Single stateless message, temperature=0, structured output via Anthropic
tool-use. See docs/design/spec-check/02-algorithm.md.

Replay shim
-----------
Every LLM call is routed through a `Caller`. The default `AnthropicCaller`
hits the API. Tests use `ReplayCaller`, which reads a recorded response from a
JSONL cassette so CI runs deterministically with no network and no API key.
Re-recording happens with `LUMO_TEST_LIVE=1` (handled in the test fixtures, not
here). This is the HTTP-cassette idea applied to the LLM boundary — the call
shape is small and fixed, so a bespoke shim is cheaper than pulling vcrpy.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol, cast

from lumo.spec.models import CONFIDENCES, FINDING_IDS, SEVERITIES

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

# Tool-use schema. tool_choice forces this single tool, which forces valid JSON
# and eliminates the "model wrapped JSON in prose" failure mode.
EMIT_FINDINGS_TOOL: dict[str, Any] = {
    "name": "emit_findings",
    "description": "Emit zero or more spec-vs-layout findings. Emit an empty "
    "list when the layout satisfies the spec.",
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": list(FINDING_IDS)},
                        "severity": {"type": "string", "enum": list(SEVERITIES)},
                        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
                        "element": {
                            "type": ["string", "null"],
                            "description": "Layout element id this finding is "
                            "about, or null if it concerns the screen as a whole.",
                        },
                        "message": {
                            "type": "string",
                            "description": "One-sentence statement of the discrepancy.",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "A VERBATIM substring of the spec text "
                            "that supports this finding. Must be copied exactly, "
                            "character-for-character, from the spec. Do not "
                            "paraphrase. Do not invent.",
                        },
                        "recommendation": {
                            "type": "string",
                            "description": "Concrete fix, with platform hints where useful.",
                        },
                    },
                    "required": [
                        "id",
                        "severity",
                        "confidence",
                        "message",
                        "evidence",
                        "recommendation",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["findings"],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = """\
You are Lumo's spec-vs-design auditor. You are given a product specification \
(Markdown) and a UI layout (JSON describing the elements on one screen). Your \
job is to report where the LAYOUT fails to satisfy what the SPEC requires.

Rules — these are non-negotiable:

1. Report ONLY what the spec explicitly or implicitly requires. NEVER invent \
requirements. Forbidden examples:
   - "Spec doesn't mention dark mode; layout should support it." (NO)
   - "Best practice is to include error states." (NO)
   - "Modern apps usually have a back button." (NO)
   If a requirement is not in the spec, it does not exist for this check.

2. Every finding MUST include an `evidence` field that is a VERBATIM substring \
of the spec text — copied exactly, character-for-character. Never paraphrase, \
never fabricate a quote. If you cannot quote the spec for a finding, do not \
emit it.

3. Set `confidence`:
   - "high"   only when the evidence quote DIRECTLY STATES the requirement.
   - "medium" when the spec implies it but does not state it outright. This is \
the default.
   - "low"    for soft heuristics where you are guessing.
   Inferred-severity findings must never be "high" confidence.

4. Pick `severity`. If the spec uses RFC 2119 wording, map it: \
must/required/shall -> high; should/recommended -> medium; \
may/optional/nice-to-have -> low. Most product specs do NOT use that wording — \
infer from context, and when you infer, set confidence to medium or low.

5. Use one of these finding ids, nothing else:
   - missing_required_element: spec names a UI element/state/control absent from the layout.
   - element_count_mismatch: spec quantifies (e.g. "3 fields") and the layout count differs.
   - behavioural_constraint_violation: spec describes state/visibility/order the layout violates.
   - copy_mismatch: spec quotes specific text; the layout shows different text.
   - extraneous_element: layout has elements the spec does not mention (default low confidence — the spec may simply be incomplete).
   - ambiguous_requirement: the spec is genuinely unclear; flag for a human, not as a defect.

6. The spec may reference images you cannot see (rendered as `![...]()` \
placeholders). Lower confidence on findings that depend on such visual content; \
do not assert what an image shows.

When the layout satisfies the spec, emit an empty findings list. Do not invent \
findings to look useful.

Always call the emit_findings tool. Never reply in prose."""


def build_user_message(spec_markdown: str, layout: dict[str, Any]) -> str:
    """Assemble the user message: spec text + pretty-printed layout."""
    layout_json = json.dumps(layout, indent=2, ensure_ascii=False)
    return (
        "<spec>\n"
        f"{spec_markdown}\n"
        "</spec>\n\n"
        "<layout>\n"
        f"{layout_json}\n"
        "</layout>\n\n"
        "Audit the layout against the spec. Call emit_findings."
    )


@dataclass
class LLMResult:
    findings: list[dict[str, Any]]
    input_tokens: int | None
    output_tokens: int | None


class LLMError(RuntimeError):
    """Raised on unrecoverable LLM failure (after the single retry)."""


class Caller(Protocol):
    def call(self, system: list[dict[str, Any]], user: str, model: str) -> LLMResult: ...


class AnthropicCaller:
    """Live Anthropic API caller.

    Reads the key from LUMO_ANTHROPIC_API_KEY (falling back to
    ANTHROPIC_API_KEY) and an optional Anthropic-compatible base URL from
    LUMO_ANTHROPIC_BASE_URL (LiteLLM / Bedrock gateway / internal proxy).
    """

    def __init__(self, base_url: str | None = None) -> None:
        try:
            import anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise LLMError(
                "the 'anthropic' package is required for live spec checks "
                "(pip install anthropic)"
            ) from exc

        api_key = os.environ.get("LUMO_ANTHROPIC_API_KEY") or os.environ.get(
            "ANTHROPIC_API_KEY"
        )
        if not api_key:
            raise LLMError(
                "no API key — set LUMO_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY)."
            )
        base = base_url or os.environ.get("LUMO_ANTHROPIC_BASE_URL")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base:
            kwargs["base_url"] = base
        self._client = anthropic.Anthropic(**kwargs)

    def call(self, system: list[dict[str, Any]], user: str, model: str) -> LLMResult:
        # The dict schemas (system blocks, tool, tool_choice) match the
        # Anthropic typed params structurally; cast keeps the schema dict-defined
        # (shared with tests + the future MCP wrapper) without a per-field rebuild.
        resp = self._client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=cast("Any", system),
            tools=cast("Any", [EMIT_FINDINGS_TOOL]),
            tool_choice=cast("Any", {"type": "tool", "name": "emit_findings"}),
            messages=[{"role": "user", "content": user}],
        )
        findings = _extract_tool_input(resp)
        usage = getattr(resp, "usage", None)
        return LLMResult(
            findings=findings,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )


def _extract_tool_input(resp: Any) -> list[dict[str, Any]]:
    """Pull the emit_findings tool input out of an Anthropic response."""
    for block in getattr(resp, "content", []):
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_findings":
            data = block.input
            findings = data.get("findings", []) if isinstance(data, dict) else []
            if not isinstance(findings, list):
                raise LLMError("model returned a non-list 'findings'")
            return findings
    raise LLMError("model did not call emit_findings")


def run_llm(
    *,
    caller: Caller,
    spec_markdown: str,
    layout: dict[str, Any],
    model: str,
) -> LLMResult:
    """Run one spec check. Retries once on an LLM-layer error, then raises.

    The system prompt is fixed across all invocations, so it is marked as a
    prompt-cache candidate (cache_control: ephemeral). Cache savings depend on
    hit rate and are measured during dogfood, not asserted here.
    """
    system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    user = build_user_message(spec_markdown, layout)

    last_exc: Exception | None = None
    for _ in range(2):
        try:
            return caller.call(system, user, model)
        except LLMError as exc:
            last_exc = exc
    raise LLMError(f"LLM call failed after retry: {last_exc}")
