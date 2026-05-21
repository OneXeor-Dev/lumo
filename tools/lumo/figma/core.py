"""Figma REST API client — token diff + frame render.

Two distinct subcommands live here:

  - **`diff`** (shipped 0.0.8) — Figma variables → diff against a
    `lumo-audit` JSON. Match by VALUE, not name (Figma `spacing/lg`
    vs code `Dimens.lg.dp` drifts naturally). Three buckets:
    matched / unused_in_code / missing_from_figma. Variables only —
    COLOR + FLOAT supported, STRING + BOOLEAN deferred (no clean
    code-side equivalent yet).

  - **`render`** (shipped 0.2.0) — Figma frame → Lumo layout JSON
    with `source: "measured"`. Hits `/v1/files/{key}/nodes?ids={id}`,
    walks the subtree, normalises coordinates to the root frame's
    origin, emits the same schema `lumo-render compose/swiftui`
    produce. Unlocks design audit BEFORE code ships — feed the
    output to `lumo-theory check --layout` for cognitive-science
    findings on the Figma design itself.

Out of scope (across both subcommands):
  - **Styles** (the older Figma token system before variables). Heavy
    node-tree walk; deferred until variables coverage proves the diff
    model.
  - **Pixel diff** of Figma frame vs the rendered app — runtime
    territory, lives behind `snapshot_input` capture libraries in
    Phase 3.
  - **Token mapping config.** Match by VALUE, not name. Naming-
    convention drift between Figma and code doesn't block the diff.
    Add a `figma.mapping` only if a real user case demands name-aware
    matching beyond value-only.

Auth:
  - Read `FIGMA_TOKEN` from the environment. Never accept the token
    via CLI args — they end up in shell history. Same env var serves
    both subcommands.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, cast
from urllib.parse import unquote, urlparse

import httpx

from lumo.render.core import Element, RenderReport

FIGMA_API_BASE = "https://api.figma.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0

VariableType = Literal["COLOR", "FLOAT", "STRING", "BOOLEAN"]


# ============================================================================
# Errors
# ============================================================================


class FigmaApiError(Exception):
    """Raised when the Figma REST API returns a non-2xx response.

    Carries the original HTTP status, the response body (truncated), and
    the endpoint we hit, so the CLI can give a human-readable message
    without dumping a stack trace.
    """

    def __init__(self, status: int, endpoint: str, body: str) -> None:
        self.status = status
        self.endpoint = endpoint
        self.body = body[:500]
        super().__init__(f"Figma API {status} on {endpoint}: {self.body}")


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass(frozen=True)
class ParsedFigmaUrl:
    """Extracted bits from a Figma share URL.

    `node_id` is normalised to API form (`12:34`) — the URL form
    (`12-34`) is converted on the way in.
    """

    file_key: str | None
    node_id: str | None


@dataclass(frozen=True)
class FigmaToken:
    """One resolved Figma variable, narrowed to the fields the diff needs.

    - `value` is the resolved value for the requested mode (always a
      concrete float / hex string, never an alias reference).
    - `value_canonical` is what we actually compare against code:
      - For COLOR — a `#RRGGBB` (uppercase) hex string with alpha dropped.
      - For FLOAT — the float itself, cast to whatever the user has in
        `lumo-audit` output.
    - `mode_name` is the human label of the mode the value came from.
    """

    id: str
    name: str
    type: VariableType
    collection: str
    mode_name: str
    value: float | str
    value_canonical: float | str
    is_alias_resolved: bool = False


@dataclass(frozen=True)
class FigmaTokens:
    """All tokens fetched from a Figma file, grouped by type.

    `colors` / `floats` carry the resolved values. `strings` / `booleans`
    are accepted by the parser but skipped in the diff for v1 — we keep
    them in the dataclass so a later phase can surface them without
    re-touching the parser.
    """

    file_key: str
    mode_label: str
    colors: tuple[FigmaToken, ...]
    floats: tuple[FigmaToken, ...]
    strings: tuple[FigmaToken, ...] = ()
    booleans: tuple[FigmaToken, ...] = ()


@dataclass(frozen=True)
class TokenMatch:
    """A Figma token whose value appears in the audited code."""

    token: FigmaToken
    code_occurrences: int  # how many times the value was seen
    code_kind: str         # "padding" | "radius" | "size" | "color"


@dataclass(frozen=True)
class UnusedToken:
    """A Figma token whose value never appears in the audited code."""

    token: FigmaToken


@dataclass(frozen=True)
class MissingFromFigma:
    """A value heavily used in code with no matching Figma token.

    Triggered only when `code_occurrences >= threshold` (default 3) —
    we don't flag every off-scale literal as a missing token, only ones
    that look like a de-facto token waiting to be promoted.
    """

    value: float | str
    code_kind: str
    code_occurrences: int


@dataclass(frozen=True)
class FigmaDiffReport:
    """Output of `diff_against_audit`."""

    file_key: str
    mode_label: str
    matched: tuple[TokenMatch, ...]
    unused_in_code: tuple[UnusedToken, ...]
    missing_from_figma: tuple[MissingFromFigma, ...]
    summary_counts: Mapping[str, int] = field(default_factory=dict)


# ============================================================================
# URL parsing
# ============================================================================


def parse_figma_url(url: str) -> ParsedFigmaUrl:
    """Extract `file_key` + `node_id` from a Figma share URL.

    Handles `/file/`, `/design/`, `/proto/`, and `/board/` paths.
    Normalises the URL's `node-id=12-34` form into the API's `12:34`.
    Returns `None` for either field when the URL doesn't carry it.
    """
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    file_key: str | None = None
    for marker in ("file", "design", "proto", "board"):
        if marker in parts:
            idx = parts.index(marker)
            if idx + 1 < len(parts):
                file_key = parts[idx + 1]
                break

    node_id: str | None = None
    match = re.search(r"node-id=([^&]+)", parsed.query)
    if match:
        node_id = unquote(match.group(1)).replace("-", ":")

    return ParsedFigmaUrl(file_key=file_key, node_id=node_id)


# ============================================================================
# HTTP client
# ============================================================================


def _resolve_token(token: str | None) -> str:
    """Pull the Figma token from the arg, falling back to FIGMA_TOKEN.

    We never accept tokens via CLI positional args (shell history) —
    the CLI passes `None` here and we read the env. The arg overload
    is kept on the Python side so tests can inject without monkeypatching
    the environment.
    """
    if token:
        return token
    env_token = os.environ.get("FIGMA_TOKEN", "").strip()
    if not env_token:
        raise FigmaApiError(
            status=401,
            endpoint="<auth>",
            body=(
                "FIGMA_TOKEN environment variable is not set. Generate a "
                "personal access token at https://www.figma.com/developers "
                "and export FIGMA_TOKEN before running lumo-figma."
            ),
        )
    return env_token


def _fetch_local_variables(
    file_key: str,
    token: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """GET /v1/files/{file_key}/variables/local.

    Returns the raw JSON body. Caller is responsible for picking out
    `meta.variables` and `meta.variableCollections`.
    """
    endpoint = f"/files/{file_key}/variables/local"
    url = f"{FIGMA_API_BASE}{endpoint}"
    headers = {"X-Figma-Token": token}

    client = http_client or httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    owns_client = http_client is None
    try:
        response = client.get(url, headers=headers)
        if response.status_code >= 400:
            raise FigmaApiError(
                status=response.status_code,
                endpoint=endpoint,
                body=response.text,
            )
        return cast(dict[str, Any], response.json())
    finally:
        if owns_client:
            client.close()


# ============================================================================
# Token resolution
# ============================================================================
#
# Variables can alias other variables: `spacing/lg` (one variable) might
# resolve to `spacing/base * 2` (another variable). We follow the chain
# until we land on a concrete COLOR / FLOAT / STRING / BOOLEAN. If we
# detect a cycle, we bail with the partially-resolved value and mark
# the token as `is_alias_resolved=False` so the diff knows not to trust
# it. Cycles in real Figma files are rare but not impossible — we'd
# rather report than crash.

_MAX_ALIAS_DEPTH = 16


def _resolve_value(
    variable_id: str,
    mode_id: str,
    variables_by_id: dict[str, dict[str, Any]],
    depth: int = 0,
    seen: tuple[str, ...] = (),
) -> tuple[Any, bool]:
    """Return (resolved_value, fully_resolved) for a variable + mode.

    `fully_resolved` is False if we hit the depth cap or a cycle.
    """
    if depth >= _MAX_ALIAS_DEPTH:
        return None, False
    if variable_id in seen:
        return None, False
    var = variables_by_id.get(variable_id)
    if var is None:
        return None, False
    values_by_mode = var.get("valuesByMode", {})
    raw = values_by_mode.get(mode_id)
    if raw is None:
        return None, False
    # Alias references are dicts with type=VARIABLE_ALIAS + id.
    if isinstance(raw, dict) and raw.get("type") == "VARIABLE_ALIAS":
        target_id = raw.get("id")
        if not isinstance(target_id, str):
            return None, False
        return _resolve_value(
            target_id,
            mode_id,
            variables_by_id,
            depth=depth + 1,
            seen=seen + (variable_id,),
        )
    return raw, True


def _canonicalise_color(raw: Any) -> str | None:
    """Convert Figma's `{r, g, b, a}` 0..1 dict into `#RRGGBB`.

    Alpha is intentionally dropped — code-side colours in `lumo-audit`
    don't carry alpha either; mismatched alphas would create false
    diff entries. If we later need alpha-aware matching we'll thread
    it through.
    """
    if not isinstance(raw, dict):
        return None
    try:
        r = float(raw["r"])
        g = float(raw["g"])
        b = float(raw["b"])
    except (KeyError, TypeError, ValueError):
        return None

    def _byte(channel: float) -> int:
        clamped = max(0.0, min(1.0, channel))
        return round(clamped * 255)

    return "#{:02X}{:02X}{:02X}".format(_byte(r), _byte(g), _byte(b))


def _canonicalise_float(raw: Any) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


# ============================================================================
# Public: fetch_tokens
# ============================================================================


def fetch_tokens(
    file_key: str,
    token: str | None = None,
    mode: str | None = None,
    http_client: httpx.Client | None = None,
) -> FigmaTokens:
    """Fetch a Figma file's local variables, resolve aliases, return tokens.

    Args:
        file_key: The Figma file key (`abc123`, from
                  `https://www.figma.com/design/abc123/...`).
        token:    Optional Figma personal access token. Falls back to
                  `FIGMA_TOKEN` env var when None.
        mode:     Variable-collection mode name (e.g. "Dark"). When None,
                  uses each collection's default mode.
        http_client: Injection point for tests; production callers leave
                  this None.
    """
    resolved_token = _resolve_token(token)
    payload = _fetch_local_variables(file_key, resolved_token, http_client)
    return _parse_tokens_payload(file_key, payload, mode)


def _parse_tokens_payload(
    file_key: str,
    payload: dict[str, Any],
    mode_name: str | None,
) -> FigmaTokens:
    """Pure function: turn a `variables/local` payload into FigmaTokens.

    Extracted so tests can feed fixture JSON without touching httpx.
    """
    meta = payload.get("meta") or {}
    variables_by_id = cast(dict[str, dict[str, Any]], meta.get("variables") or {})
    collections_by_id = cast(
        dict[str, dict[str, Any]], meta.get("variableCollections") or {}
    )

    colors: list[FigmaToken] = []
    floats: list[FigmaToken] = []
    strings: list[FigmaToken] = []
    booleans: list[FigmaToken] = []
    chosen_mode_label = mode_name or "default"

    for var_id, var in variables_by_id.items():
        var_type = var.get("resolvedType") or var.get("type")
        if var_type not in ("COLOR", "FLOAT", "STRING", "BOOLEAN"):
            continue
        collection_id = var.get("variableCollectionId")
        collection = collections_by_id.get(collection_id, {}) if collection_id else {}
        collection_name = str(collection.get("name", "")) or "<unknown collection>"

        # Pick the mode_id we resolve against. Default mode is whatever
        # the collection says, unless the caller asked for a named mode
        # that exists in this collection.
        mode_id = collection.get("defaultModeId")
        if mode_name:
            for m in collection.get("modes", []) or []:
                if str(m.get("name", "")) == mode_name:
                    mode_id = m.get("modeId")
                    break
        if not isinstance(mode_id, str):
            continue
        # Track the human label so the report is readable.
        for m in collection.get("modes", []) or []:
            if m.get("modeId") == mode_id:
                chosen_mode_label = str(m.get("name", mode_name or "default"))
                break

        raw, fully_resolved = _resolve_value(var_id, mode_id, variables_by_id)
        if raw is None:
            continue

        if var_type == "COLOR":
            canon = _canonicalise_color(raw)
            if canon is None:
                continue
            colors.append(
                FigmaToken(
                    id=var_id,
                    name=str(var.get("name", "")),
                    type="COLOR",
                    collection=collection_name,
                    mode_name=chosen_mode_label,
                    value=canon,
                    value_canonical=canon,
                    is_alias_resolved=fully_resolved,
                )
            )
        elif var_type == "FLOAT":
            canon_f = _canonicalise_float(raw)
            if canon_f is None:
                continue
            floats.append(
                FigmaToken(
                    id=var_id,
                    name=str(var.get("name", "")),
                    type="FLOAT",
                    collection=collection_name,
                    mode_name=chosen_mode_label,
                    value=canon_f,
                    value_canonical=canon_f,
                    is_alias_resolved=fully_resolved,
                )
            )
        elif var_type == "STRING":
            if not isinstance(raw, str):
                continue
            strings.append(
                FigmaToken(
                    id=var_id,
                    name=str(var.get("name", "")),
                    type="STRING",
                    collection=collection_name,
                    mode_name=chosen_mode_label,
                    value=raw,
                    value_canonical=raw,
                    is_alias_resolved=fully_resolved,
                )
            )
        elif var_type == "BOOLEAN":
            if not isinstance(raw, bool):
                continue
            booleans.append(
                FigmaToken(
                    id=var_id,
                    name=str(var.get("name", "")),
                    type="BOOLEAN",
                    collection=collection_name,
                    mode_name=chosen_mode_label,
                    value=str(raw),
                    value_canonical=str(raw),
                    is_alias_resolved=fully_resolved,
                )
            )

    colors.sort(key=lambda t: (t.collection, t.name))
    floats.sort(key=lambda t: (t.collection, t.value_canonical))
    strings.sort(key=lambda t: (t.collection, t.name))
    booleans.sort(key=lambda t: (t.collection, t.name))

    return FigmaTokens(
        file_key=file_key,
        mode_label=chosen_mode_label,
        colors=tuple(colors),
        floats=tuple(floats),
        strings=tuple(strings),
        booleans=tuple(booleans),
    )


# ============================================================================
# Diff
# ============================================================================
#
# We compare BY VALUE, not by name. Rationale:
#   - Naming conventions drift across Figma (`spacing/lg`) and code
#     (`Dimens.lg.dp`, `Theme.spacing.large`, ad-hoc `padding(24.dp)`).
#   - The value is the only stable join key.
#   - Name appears in the report for human reference; the *match* never
#     depends on it.
#
# Three buckets in the output:
#   matched         — token value appears in code (at least once).
#   unused_in_code  — token declared in Figma but no literal in audit
#                     matches it. Often deletable; sometimes a future
#                     token waiting to be adopted.
#   missing_from_figma — value used heavily in code (>= threshold) but
#                     not declared in Figma. Strong candidate for token
#                     promotion.

DEFAULT_MISSING_THRESHOLD = 3


def diff_against_audit(
    figma: FigmaTokens,
    audit_payload: Mapping[str, Any],
    missing_threshold: int = DEFAULT_MISSING_THRESHOLD,
) -> FigmaDiffReport:
    """Compare Figma tokens against a `lumo-audit` JSON payload.

    `audit_payload` is the parsed JSON the `lumo-audit scan --json`
    command emits — passing it as a dict keeps `lumo-figma` decoupled
    from the audit dataclass internals.
    """
    # Build value → (kind, occurrences) lookup from the audit's scale
    # observations. Each kind ('padding', 'radius', 'size') has its own
    # frequency table; we merge them, picking the highest count if a
    # value appears under multiple kinds (rare in practice).
    code_floats: dict[float, tuple[str, int]] = {}
    observations = audit_payload.get("scale_observations") or []
    for obs in observations:
        kind = str(obs.get("kind", ""))
        for entry in obs.get("values_by_frequency") or []:
            value = entry.get("value")
            count = entry.get("count", 0)
            if not isinstance(value, (int, float)) or not isinstance(count, int):
                continue
            existing = code_floats.get(float(value))
            if existing is None or count > existing[1]:
                code_floats[float(value)] = (kind, count)

    # Colour occurrences live in audit `findings` (hardcoded_color), not
    # in scale_observations. Aggregate per hex.
    code_colors: dict[str, int] = {}
    for finding in audit_payload.get("findings") or []:
        if finding.get("check") != "hardcoded_color":
            continue
        metric = finding.get("metric") or {}
        hex_val = metric.get("hex")
        if not isinstance(hex_val, str):
            continue
        normalised = hex_val.upper()
        if not normalised.startswith("#"):
            normalised = "#" + normalised
        code_colors[normalised] = code_colors.get(normalised, 0) + 1

    matched: list[TokenMatch] = []
    unused: list[UnusedToken] = []
    matched_values_float: set[float] = set()
    matched_values_color: set[str] = set()

    # FLOAT tokens.
    for token in figma.floats:
        value = cast(float, token.value_canonical)
        hit = code_floats.get(value)
        if hit is None:
            unused.append(UnusedToken(token=token))
            continue
        kind, occurrences = hit
        matched.append(
            TokenMatch(token=token, code_occurrences=occurrences, code_kind=kind)
        )
        matched_values_float.add(value)

    # COLOR tokens.
    for token in figma.colors:
        value_c = cast(str, token.value_canonical)
        occurrences = code_colors.get(value_c, 0)
        if occurrences == 0:
            unused.append(UnusedToken(token=token))
            continue
        matched.append(
            TokenMatch(token=token, code_occurrences=occurrences, code_kind="color")
        )
        matched_values_color.add(value_c)

    # Missing from Figma — heavy code values that no token matched.
    missing: list[MissingFromFigma] = []
    for value, (kind, occurrences) in code_floats.items():
        if value in matched_values_float:
            continue
        if occurrences < missing_threshold:
            continue
        missing.append(
            MissingFromFigma(
                value=value,
                code_kind=kind,
                code_occurrences=occurrences,
            )
        )
    for hex_val, occurrences in code_colors.items():
        if hex_val in matched_values_color:
            continue
        if occurrences < missing_threshold:
            continue
        missing.append(
            MissingFromFigma(
                value=hex_val,
                code_kind="color",
                code_occurrences=occurrences,
            )
        )

    matched.sort(
        key=lambda m: (m.code_kind, -m.code_occurrences, str(m.token.name))
    )
    unused.sort(key=lambda u: (u.token.type, u.token.collection, u.token.name))
    missing.sort(key=lambda m: (m.code_kind, -m.code_occurrences))

    counts = {
        "matched": len(matched),
        "unused_in_code": len(unused),
        "missing_from_figma": len(missing),
    }

    return FigmaDiffReport(
        file_key=figma.file_key,
        mode_label=figma.mode_label,
        matched=tuple(matched),
        unused_in_code=tuple(unused),
        missing_from_figma=tuple(missing),
        summary_counts=counts,
    )


# ============================================================================
# Figma layout render
# ============================================================================
#
# `lumo-figma render` turns a Figma frame into a Lumo layout JSON with
# `source: "measured"`. The downstream toolchain (`lumo-theory`,
# `lumo-parity`) consumes the result unchanged. This is the missing
# piece for "design audit without code" — Fitts / Hick / Gestalt /
# reach checks against the Figma file directly, before a single line
# ships. Honesty rule: we never invent coordinates; nodes Figma cannot
# measure (auto-layout placeholders with null `absoluteBoundingBox`)
# are skipped, not faked.

# Maximum recursion depth when walking the Figma node tree. 200 covers
# every realistic mobile screen; the cap exists to prevent runaway
# walks on broken / cyclic API responses.
_FIGMA_RENDER_MAX_DEPTH = 200

# Figma node types we treat as having a renderable box. Other types
# (DOCUMENT, CANVAS, SECTION wrapper) are walked but not emitted.
_FIGMA_RENDERABLE_TYPES = frozenset({
    "FRAME", "GROUP", "COMPONENT", "COMPONENT_SET", "INSTANCE",
    "RECTANGLE", "ELLIPSE", "REGULAR_POLYGON", "STAR", "VECTOR",
    "LINE", "TEXT", "BOOLEAN_OPERATION", "STAMP", "SLICE",
})

# Container types whose name should be propagated as `group` to
# descendant elements. The root frame's name is NOT used as group —
# it's the screen, not a sub-group.
_FIGMA_GROUP_TYPES = frozenset({
    "FRAME", "GROUP", "COMPONENT", "COMPONENT_SET", "SECTION",
})


def _fetch_node(
    file_key: str,
    node_id: str,
    token: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """GET /v1/files/{file_key}/nodes?ids={node_id}. One round trip.

    Returns the raw JSON; the caller picks `["nodes"][node_id]["document"]`.
    """
    endpoint = f"/files/{file_key}/nodes"
    url = f"{FIGMA_API_BASE}{endpoint}"
    headers = {"X-Figma-Token": token}
    params = {"ids": node_id}

    client = http_client or httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    owns_client = http_client is None
    try:
        resp = client.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            raise FigmaApiError(
                status=resp.status_code,
                endpoint=f"{endpoint}?ids={node_id}",
                body=resp.text,
            )
        return cast(dict[str, Any], resp.json())
    finally:
        if owns_client:
            client.close()


_ID_SANITISE_RE = re.compile(r"[^A-Za-z0-9_]+")


def _sanitise_id(name: str, fallback: str) -> str:
    """Slugify a Figma layer name to a safe element id.

    "Btn / Continue" → "btn_continue". Empty / all-punct → fallback.
    """
    if not name:
        return fallback
    slug = _ID_SANITISE_RE.sub("_", name).strip("_").lower()
    return slug or fallback


def _figma_role(node: Mapping[str, Any], name_lower: str) -> str:
    """Best-effort role heuristic from node type + name. Documented in
    docs/design/figma-render.md §"Role heuristic".

    Order matters — first match wins. Users override by renaming layers.
    """
    ntype = node.get("type", "")
    if name_lower.startswith("btn_") or "button" in name_lower or (
        ntype == "INSTANCE" and "btn" in name_lower
    ):
        return "primary_action"
    if name_lower.startswith("nav_") or "tab_bar" in name_lower or "bottom_nav" in name_lower:
        return "nav_item"
    if name_lower.startswith("icon_") or (
        ntype == "VECTOR" and _is_square(node)
    ):
        return "icon"
    if name_lower.startswith("input_") or "field" in name_lower or "textfield" in name_lower:
        return "input"
    if ntype == "TEXT":
        return "text"
    if ntype in ("RECTANGLE", "VECTOR", "ELLIPSE", "REGULAR_POLYGON", "STAR"):
        return "image"
    return "decorative"


def _is_square(node: Mapping[str, Any]) -> bool:
    """True when the node's bbox is square-ish (within 10% tolerance)."""
    bbox = node.get("absoluteBoundingBox") or {}
    w = float(bbox.get("width") or 0.0)
    h = float(bbox.get("height") or 0.0)
    if w <= 0 or h <= 0:
        return False
    return bool(abs(w - h) / max(w, h) < 0.1)


@dataclass(frozen=True)
class _FigmaWalkStats:
    nodes_seen: int = 0
    nodes_skipped_invisible: int = 0
    nodes_skipped_no_bbox: int = 0
    truncated_depth: bool = False


def _walk_figma_tree(
    root_node: Mapping[str, Any],
) -> tuple[tuple[Element, ...], dict[str, float], _FigmaWalkStats]:
    """Recursively walk a Figma node tree, return Lumo layout elements
    plus the root frame's (width, height) for `screen`.

    The root's `absoluteBoundingBox.x/y` is subtracted from every
    descendant so the root sits at (0, 0). Honesty rule: nodes without
    a measurable bounding box are skipped; counts surface in stats.
    """
    root_bbox = root_node.get("absoluteBoundingBox") or {}
    if not root_bbox:
        raise FigmaApiError(
            status=200,
            endpoint="<render>",
            body=(
                f"Figma node {root_node.get('id')!r} has no "
                "absoluteBoundingBox — cannot render an unmeasured frame."
            ),
        )
    origin_x = float(root_bbox.get("x", 0.0))
    origin_y = float(root_bbox.get("y", 0.0))
    screen_dims = {
        "width": float(root_bbox.get("width", 0.0)),
        "height": float(root_bbox.get("height", 0.0)),
    }

    elements: list[Element] = []
    id_counter: dict[str, int] = {}
    nodes_seen = 0
    skipped_invisible = 0
    skipped_no_bbox = 0
    truncated = False

    def visit(node: Mapping[str, Any], parent_group: str | None, depth: int) -> None:
        nonlocal nodes_seen, skipped_invisible, skipped_no_bbox, truncated
        if depth > _FIGMA_RENDER_MAX_DEPTH:
            truncated = True
            return
        nodes_seen += 1
        # Skip hidden layers — they don't ship.
        if node.get("visible") is False:
            skipped_invisible += 1
            return
        ntype = node.get("type", "")
        name = (node.get("name") or "").strip()
        name_lower = name.lower().replace(" ", "_").replace("/", "_")

        # Decide whether THIS node emits an element. The root frame
        # itself isn't emitted (it's the screen), only its descendants.
        is_root = depth == 0
        if not is_root and ntype in _FIGMA_RENDERABLE_TYPES:
            bbox = node.get("absoluteBoundingBox")
            if bbox is None:
                skipped_no_bbox += 1
                # Even with no bbox, walk children — they may have their own.
            else:
                role = _figma_role(node, name_lower)
                fallback_id = f"{role}_{id_counter.get(role, 0) + 1}"
                eid = _sanitise_id(name, fallback_id)
                # Keep the counter regardless so collisions get _2, _3
                id_counter[role] = id_counter.get(role, 0) + 1
                # If the sanitised id collides with a previously emitted one,
                # append a counter suffix.
                base_eid = eid
                seen_ids = {e.id for e in elements}
                suffix = 2
                while eid in seen_ids:
                    eid = f"{base_eid}_{suffix}"
                    suffix += 1
                elements.append(Element(
                    id=eid,
                    role=role,
                    x=float(bbox["x"]) - origin_x,
                    y=float(bbox["y"]) - origin_y,
                    w=float(bbox["width"]),
                    h=float(bbox["height"]),
                    source="ast-resolved",  # placeholder; overridden below
                    group=parent_group,
                ))

        # Determine the group hint we pass to children.
        if ntype in _FIGMA_GROUP_TYPES and not is_root:
            child_group = _sanitise_id(name, "") or parent_group
        else:
            child_group = parent_group

        for child in node.get("children", []) or []:
            visit(child, child_group, depth + 1)

    visit(root_node, None, depth=0)

    # Stamp all elements as `source: "measured"` — Figma's bbox IS
    # measurement, not a static guess. Replace the placeholder we used
    # in the constructor (Element.source is a frozen Literal; rebuild).
    measured_elements = tuple(
        Element(
            id=e.id,
            role=e.role,
            x=e.x, y=e.y, w=e.w, h=e.h,
            source="measured",
            group=e.group,
            weight=e.weight,
            reason=e.reason,
        )
        for e in elements
    )

    stats = _FigmaWalkStats(
        nodes_seen=nodes_seen,
        nodes_skipped_invisible=skipped_invisible,
        nodes_skipped_no_bbox=skipped_no_bbox,
        truncated_depth=truncated,
    )
    return measured_elements, screen_dims, stats


def fetch_node_layout(
    file_key: str,
    node_id: str,
    *,
    token: str | None = None,
    screen_width: float | None = None,
    screen_height: float | None = None,
    http_client: httpx.Client | None = None,
) -> RenderReport:
    """Hit Figma's `/v1/files/{file_key}/nodes?ids={node_id}` endpoint
    and turn the response into a Lumo `RenderReport`.

    `screen_width` / `screen_height` override the root frame's natural
    dimensions when you want to clamp a Figma frame to a specific mobile
    resolution (e.g. Figma frame is 1440px wide but you want to apply
    `lumo-theory check` at 411dp).

    Returns a `RenderReport` with `source: "measured"` on every element.
    """
    resolved_token = _resolve_token(token)
    payload = _fetch_node(file_key, node_id, resolved_token, http_client)
    return _parse_node_layout_payload(
        payload,
        node_id,
        screen_width=screen_width,
        screen_height=screen_height,
    )


def _parse_node_layout_payload(
    payload: Mapping[str, Any],
    node_id: str,
    *,
    screen_width: float | None = None,
    screen_height: float | None = None,
) -> RenderReport:
    """Pure transform from a Figma `/nodes` response to RenderReport.

    Extracted so tests can feed fixture JSON without touching httpx.
    """
    nodes = payload.get("nodes") or {}
    entry = nodes.get(node_id)
    if entry is None:
        raise FigmaApiError(
            status=200,
            endpoint=f"<render:{node_id}>",
            body=(
                f"Figma response does not contain node_id={node_id!r}. "
                f"Got keys: {sorted(nodes.keys())!r}"
            ),
        )
    document = entry.get("document")
    if document is None:
        raise FigmaApiError(
            status=200,
            endpoint=f"<render:{node_id}>",
            body=f"Figma node {node_id!r} has no 'document' field.",
        )

    elements, screen_dims, _stats = _walk_figma_tree(document)
    return RenderReport(
        screen_width=screen_width if screen_width is not None else screen_dims["width"],
        screen_height=screen_height if screen_height is not None else screen_dims["height"],
        unit="dp",  # Figma units map to dp/pt; we expose as dp for parity downstream
        elements=elements,
    )
