"""Figma — design-system sync via the Figma REST API.

Compares the design tokens declared in a Figma file (variables and styles)
against what the codebase actually uses (a `lumo-audit` report or a live
repo scan). Three buckets in the diff:

  - matched          — token value present in Figma and in code
  - unused_in_code   — token declared in Figma but no literal in the
                       codebase matches its value
  - missing_from_figma — value used many times in the code but not
                       declared as a token in Figma

Comparison is by **value**, not by name — different naming conventions
across Figma / Compose / SwiftUI are common, so the only reliable join
key is the resolved number / hex string. The name is surfaced in the
report for human reference, but never required for the match.

Public API:
    parse_figma_url(url)              -> ParsedFigmaUrl
    fetch_tokens(file_key, token=...) -> FigmaTokens
    diff_against_audit(figma, audit)  -> FigmaDiffReport
"""

from lumo.figma.core import (
    FigmaApiError,
    FigmaDiffReport,
    FigmaToken,
    FigmaTokens,
    ParsedFigmaUrl,
    diff_against_audit,
    fetch_tokens,
    parse_figma_url,
)

__all__ = [
    "FigmaApiError",
    "FigmaDiffReport",
    "FigmaToken",
    "FigmaTokens",
    "ParsedFigmaUrl",
    "diff_against_audit",
    "fetch_tokens",
    "parse_figma_url",
]
