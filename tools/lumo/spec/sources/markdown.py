"""Markdown spec source.

No HTTP, no auth. Used for offline / OSS testing and the monorepo case where
the spec is checked into the repo alongside the code. The file is already
Markdown, so flattening is a passthrough; the only work is deriving a title
(first H1, falling back to the filename).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from lumo.spec.models import SpecDocument

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


class MarkdownSource:
    name = "markdown"

    def fetch(self, identifier: str) -> SpecDocument:
        """Read a Markdown file at `identifier` and wrap it in a SpecDocument."""
        path = Path(identifier)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"spec file not found: {identifier}") from exc

        match = _H1.search(text)
        title = match.group(1).strip() if match else path.name

        return SpecDocument(
            source_type="markdown",
            source_id=str(path),
            title=title,
            markdown=text,
            fetched_at=datetime.now(timezone.utc),
            raw_url=None,
        )
