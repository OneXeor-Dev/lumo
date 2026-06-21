"""lumo-spec — semantic spec-vs-layout check (LLM-backed).

The first Lumo tool that depends on an LLM at runtime. The honesty contract
(see docs/design/spec-check/05-honesty.md) makes that explicit: every finding's
`source` is always "llm-derived", carries a `confidence` level and a verbatim
`evidence` quote validated as a substring of the fetched spec text.

Phase 1 ships the Markdown source + the full LLM round-trip. Confluence, Jira,
and the MCP wrapper land in later phases.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.2.3"
