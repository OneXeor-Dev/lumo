"""LLM record/replay shim for deterministic, offline tests.

The spec-check LLM call is a single stateless request, so a full HTTP-cassette
library (vcrpy / respx) is overkill. This shim records and replays at the
`Caller` boundary instead: a cassette is a JSONL file where each line is one
recorded call keyed by a hash of (model, system, user).

- `ReplayCaller(cassette)` reads responses; raises if a call is unrecorded.
- `RecordingCaller(inner, cassette)` wraps a live caller, appending each new
  call to the cassette. Used only when re-recording (LUMO_TEST_LIVE=1 in the
  test fixtures), never on CI.

Cassettes are version-controlled, so a model upgrade that changes responses
shows up as a visible diff in PR review.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lumo.spec.llm import Caller, LLMError, LLMResult


def _key(system: list[dict[str, Any]], user: str, model: str) -> str:
    system_text = "\n".join(b.get("text", "") for b in system)
    blob = json.dumps([model, system_text, user], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ReplayCaller:
    """Replays recorded responses from a cassette. No network."""

    def __init__(self, cassette: str | Path) -> None:
        self._by_key: dict[str, dict[str, Any]] = {}
        path = Path(cassette)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                self._by_key[rec["key"]] = rec["response"]

    def call(self, system: list[dict[str, Any]], user: str, model: str) -> LLMResult:
        key = _key(system, user, model)
        rec = self._by_key.get(key)
        if rec is None:
            raise LLMError(
                "no recorded LLM response for this call (cassette miss). "
                "Re-record with LUMO_TEST_LIVE=1."
            )
        return LLMResult(
            findings=rec.get("findings", []),
            input_tokens=rec.get("input_tokens"),
            output_tokens=rec.get("output_tokens"),
        )


class RecordingCaller:
    """Wraps a live caller, appending each call to a cassette."""

    def __init__(self, inner: Caller, cassette: str | Path) -> None:
        self._inner = inner
        self._path = Path(cassette)

    def call(self, system: list[dict[str, Any]], user: str, model: str) -> LLMResult:
        result = self._inner.call(system, user, model)
        rec = {
            "key": _key(system, user, model),
            "response": {
                "findings": result.findings,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return result
