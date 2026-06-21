"""Spec source plugins.

Each plugin returns a `SpecDocument` with the flattening guarantees from
docs/design/spec-check/01-inputs.md. Adding a source (Notion, Linear) is a new
file here plus a registry entry — no core changes.

Phase 1 ships only `markdown`. Confluence and Jira land in Phases 2 and 3.
"""

from __future__ import annotations

from typing import Protocol

from lumo.spec.models import SpecDocument
from lumo.spec.sources.markdown import MarkdownSource

__all__ = ["SpecDocument", "MarkdownSource", "SpecSource", "get_source", "SourceError"]


class SourceError(RuntimeError):
    """Raised when a source cannot be resolved or fetched."""


class SpecSource(Protocol):
    name: str

    def fetch(self, identifier: str) -> SpecDocument: ...


# Registry. Phases 2/3 append "confluence" and "jira".
_SOURCES: dict[str, type[SpecSource]] = {
    "markdown": MarkdownSource,
}


def get_source(name: str) -> type[SpecSource]:
    """Return the source plugin class for `name`, or raise SourceError."""
    try:
        return _SOURCES[name]
    except KeyError:
        available = ", ".join(sorted(_SOURCES))
        raise SourceError(
            f"unknown source '{name}'. Available in this build: {available}."
        ) from None
