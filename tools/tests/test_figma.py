"""Tests for lumo.figma — Figma API client + diff against lumo-audit.

We never call the real Figma API in tests:
  - URL parsing, alias resolution, mode selection, and diff math are
    pure functions; they're exercised against in-memory dicts.
  - The HTTP layer is tested via an httpx.MockTransport that returns
    fixture JSON without touching the network. CI without FIGMA_TOKEN
    still gets full coverage.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from lumo.figma.core import (
    FIGMA_API_BASE,
    FigmaApiError,
    FigmaToken,
    FigmaTokens,
    _parse_tokens_payload,
    diff_against_audit,
    fetch_tokens,
    parse_figma_url,
)


# ============================================================================
# URL parsing
# ============================================================================


@pytest.mark.parametrize(
    "url, expected_file_key, expected_node_id",
    [
        ("https://www.figma.com/design/ABC123/My-File?node-id=12-34", "ABC123", "12:34"),
        ("https://www.figma.com/file/ABC123/My-File", "ABC123", None),
        ("https://www.figma.com/proto/ABC123/X?node-id=5-7&t=foo", "ABC123", "5:7"),
        ("https://www.figma.com/board/XYZ/Whiteboard", "XYZ", None),
        ("https://example.com/not-figma", None, None),
        ("https://www.figma.com/design/ABC/My?node-id=12%3A34", "ABC", "12:34"),
    ],
)
def test_parse_figma_url_extracts_known_shapes(
    url: str, expected_file_key: str | None, expected_node_id: str | None
) -> None:
    parsed = parse_figma_url(url)
    assert parsed.file_key == expected_file_key
    assert parsed.node_id == expected_node_id


# ============================================================================
# Token payload parsing (pure)
# ============================================================================


def _make_payload(
    variables: dict[str, dict[str, Any]],
    collections: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {"meta": {"variables": variables, "variableCollections": collections}}


def test_parse_payload_extracts_color_and_float_tokens() -> None:
    payload = _make_payload(
        variables={
            "1:1": {
                "name": "color/primary",
                "resolvedType": "COLOR",
                "variableCollectionId": "C1",
                "valuesByMode": {"M_LIGHT": {"r": 0.231, "g": 0.510, "b": 0.965, "a": 1.0}},
            },
            "1:2": {
                "name": "spacing/lg",
                "resolvedType": "FLOAT",
                "variableCollectionId": "C2",
                "valuesByMode": {"M_DEFAULT": 24.0},
            },
        },
        collections={
            "C1": {"name": "Brand", "defaultModeId": "M_LIGHT", "modes": [{"modeId": "M_LIGHT", "name": "Light"}]},
            "C2": {"name": "Spacing", "defaultModeId": "M_DEFAULT", "modes": [{"modeId": "M_DEFAULT", "name": "default"}]},
        },
    )
    tokens = _parse_tokens_payload("FILE", payload, mode_name=None)
    assert len(tokens.colors) == 1
    assert tokens.colors[0].name == "color/primary"
    assert tokens.colors[0].value_canonical == "#3B82F6"
    assert tokens.colors[0].mode_name == "Light"
    assert len(tokens.floats) == 1
    assert tokens.floats[0].name == "spacing/lg"
    assert tokens.floats[0].value_canonical == 24.0


def test_parse_payload_resolves_alias_chain() -> None:
    # spacing/lg → spacing/base → 8.0
    payload = _make_payload(
        variables={
            "lg": {
                "name": "spacing/lg",
                "resolvedType": "FLOAT",
                "variableCollectionId": "C",
                "valuesByMode": {"M": {"type": "VARIABLE_ALIAS", "id": "base"}},
            },
            "base": {
                "name": "spacing/base",
                "resolvedType": "FLOAT",
                "variableCollectionId": "C",
                "valuesByMode": {"M": 8.0},
            },
        },
        collections={"C": {"name": "S", "defaultModeId": "M", "modes": [{"modeId": "M", "name": "default"}]}},
    )
    tokens = _parse_tokens_payload("F", payload, mode_name=None)
    lg = next(t for t in tokens.floats if t.name == "spacing/lg")
    assert lg.value_canonical == 8.0
    assert lg.is_alias_resolved is True


def test_parse_payload_handles_alias_cycle_gracefully() -> None:
    # A → B → A: must not infinite-loop, must return without producing
    # a corrupted token.
    payload = _make_payload(
        variables={
            "A": {
                "name": "a",
                "resolvedType": "FLOAT",
                "variableCollectionId": "C",
                "valuesByMode": {"M": {"type": "VARIABLE_ALIAS", "id": "B"}},
            },
            "B": {
                "name": "b",
                "resolvedType": "FLOAT",
                "variableCollectionId": "C",
                "valuesByMode": {"M": {"type": "VARIABLE_ALIAS", "id": "A"}},
            },
        },
        collections={"C": {"name": "C", "defaultModeId": "M", "modes": [{"modeId": "M", "name": "default"}]}},
    )
    tokens = _parse_tokens_payload("F", payload, mode_name=None)
    # Both end up unresolved (raw is None); neither appears as a usable
    # token.
    assert tokens.floats == ()


def test_parse_payload_selects_named_mode_when_present() -> None:
    payload = _make_payload(
        variables={
            "1": {
                "name": "color/bg",
                "resolvedType": "COLOR",
                "variableCollectionId": "C",
                "valuesByMode": {
                    "L": {"r": 1.0, "g": 1.0, "b": 1.0},
                    "D": {"r": 0.0, "g": 0.0, "b": 0.0},
                },
            },
        },
        collections={
            "C": {
                "name": "Theme",
                "defaultModeId": "L",
                "modes": [
                    {"modeId": "L", "name": "Light"},
                    {"modeId": "D", "name": "Dark"},
                ],
            }
        },
    )
    light = _parse_tokens_payload("F", payload, mode_name=None)
    assert light.colors[0].value_canonical == "#FFFFFF"
    assert light.mode_label == "Light"

    dark = _parse_tokens_payload("F", payload, mode_name="Dark")
    assert dark.colors[0].value_canonical == "#000000"
    assert dark.mode_label == "Dark"


def test_parse_payload_skips_unknown_types() -> None:
    # `resolvedType` outside our four supported types is dropped silently.
    payload = _make_payload(
        variables={
            "1": {
                "name": "weird",
                "resolvedType": "VECTOR",
                "variableCollectionId": "C",
                "valuesByMode": {"M": "anything"},
            },
        },
        collections={"C": {"name": "X", "defaultModeId": "M", "modes": [{"modeId": "M", "name": "default"}]}},
    )
    tokens = _parse_tokens_payload("F", payload, mode_name=None)
    assert tokens.colors == ()
    assert tokens.floats == ()


# ============================================================================
# fetch_tokens via httpx.MockTransport
# ============================================================================


def _mock_transport(payload: dict[str, Any], expected_token: str = "tok") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Figma-Token") == expected_token
        assert request.url.host == "api.figma.com"
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_fetch_tokens_passes_token_header_and_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_payload(
        variables={
            "1": {
                "name": "spacing/md",
                "resolvedType": "FLOAT",
                "variableCollectionId": "C",
                "valuesByMode": {"M": 16.0},
            }
        },
        collections={"C": {"name": "S", "defaultModeId": "M", "modes": [{"modeId": "M", "name": "default"}]}},
    )
    client = httpx.Client(transport=_mock_transport(payload, expected_token="figd_abc"))
    tokens = fetch_tokens("FILE", token="figd_abc", http_client=client)
    client.close()
    assert isinstance(tokens, FigmaTokens)
    assert len(tokens.floats) == 1
    assert tokens.floats[0].value_canonical == 16.0


def test_fetch_tokens_raises_on_4xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"err": "forbidden"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FigmaApiError) as exc_info:
        fetch_tokens("FILE", token="bad", http_client=client)
    client.close()
    assert exc_info.value.status == 403


def test_fetch_tokens_falls_back_to_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_payload({}, {})
    monkeypatch.setenv("FIGMA_TOKEN", "figd_env")
    client = httpx.Client(transport=_mock_transport(payload, expected_token="figd_env"))
    fetch_tokens("FILE", token=None, http_client=client)
    client.close()


def test_fetch_tokens_raises_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIGMA_TOKEN", raising=False)
    with pytest.raises(FigmaApiError) as exc_info:
        fetch_tokens("FILE")
    assert exc_info.value.status == 401


# ============================================================================
# diff_against_audit
# ============================================================================


def _audit_payload(
    padding: list[tuple[float, int]] | None = None,
    radius: list[tuple[float, int]] | None = None,
    colors: list[tuple[str, int]] | None = None,
) -> dict[str, Any]:
    """Build a synthetic lumo-audit --json payload for diff tests."""
    observations: list[dict[str, Any]] = []
    if padding:
        observations.append({
            "kind": "padding",
            "total_literals": sum(c for _, c in padding),
            "values_by_frequency": [{"value": v, "count": c} for v, c in padding],
        })
    if radius:
        observations.append({
            "kind": "radius",
            "total_literals": sum(c for _, c in radius),
            "values_by_frequency": [{"value": v, "count": c} for v, c in radius],
        })
    findings: list[dict[str, Any]] = []
    for hex_val, count in (colors or []):
        for _ in range(count):
            findings.append({
                "check": "hardcoded_color",
                "metric": {"hex": hex_val},
            })
    return {"scale_observations": observations, "findings": findings}


def _figma_with(
    *,
    colors: list[tuple[str, str]] = (),
    floats: list[tuple[str, float]] = (),
) -> FigmaTokens:
    color_tokens = tuple(
        FigmaToken(
            id=f"c{i}", name=name, type="COLOR", collection="X",
            mode_name="default", value=hex_val, value_canonical=hex_val,
            is_alias_resolved=True,
        )
        for i, (name, hex_val) in enumerate(colors)
    )
    float_tokens = tuple(
        FigmaToken(
            id=f"f{i}", name=name, type="FLOAT", collection="X",
            mode_name="default", value=val, value_canonical=val,
            is_alias_resolved=True,
        )
        for i, (name, val) in enumerate(floats)
    )
    return FigmaTokens(
        file_key="F",
        mode_label="default",
        colors=color_tokens,
        floats=float_tokens,
    )


def test_diff_matches_float_token_by_value() -> None:
    figma = _figma_with(floats=[("spacing/lg", 24.0)])
    audit = _audit_payload(padding=[(24.0, 5), (16.0, 10)])
    report = diff_against_audit(figma, audit)
    assert report.summary_counts["matched"] == 1
    assert report.matched[0].token.name == "spacing/lg"
    assert report.matched[0].code_occurrences == 5
    assert report.matched[0].code_kind == "padding"


def test_diff_flags_unused_token() -> None:
    # 99 is declared in Figma, never used in code → unused_in_code.
    figma = _figma_with(floats=[("spacing/never", 99.0)])
    audit = _audit_payload(padding=[(16.0, 5)])
    report = diff_against_audit(figma, audit)
    assert report.summary_counts["unused_in_code"] == 1
    assert report.unused_in_code[0].token.name == "spacing/never"


def test_diff_flags_missing_from_figma_when_above_threshold() -> None:
    figma = _figma_with(floats=[("spacing/lg", 24.0)])
    audit = _audit_payload(padding=[(24.0, 5), (13.0, 7)])
    report = diff_against_audit(figma, audit, missing_threshold=3)
    missing_values = [m.value for m in report.missing_from_figma]
    assert 13.0 in missing_values
    assert 24.0 not in missing_values  # matched, not missing


def test_diff_ignores_missing_below_threshold() -> None:
    # 13.0 only used twice, threshold is 3 → not flagged as missing.
    figma = _figma_with(floats=[("spacing/lg", 24.0)])
    audit = _audit_payload(padding=[(24.0, 5), (13.0, 2)])
    report = diff_against_audit(figma, audit, missing_threshold=3)
    assert report.missing_from_figma == ()


def test_diff_matches_color_by_normalised_hex() -> None:
    figma = _figma_with(colors=[("color/primary", "#3B82F6")])
    # Audit emits lowercase hex; diff must normalise to upper before comparing.
    audit = _audit_payload(colors=[("#3b82f6", 4)])
    report = diff_against_audit(figma, audit, missing_threshold=99)
    assert report.summary_counts["matched"] == 1
    assert report.matched[0].code_occurrences == 4
    assert report.matched[0].code_kind == "color"


def test_diff_color_not_in_figma_is_flagged_missing() -> None:
    figma = _figma_with(colors=[("color/primary", "#3B82F6")])
    audit = _audit_payload(colors=[("#AA0000", 5)])
    report = diff_against_audit(figma, audit, missing_threshold=3)
    assert report.summary_counts["unused_in_code"] == 1
    assert any(m.value == "#AA0000" for m in report.missing_from_figma)


def test_diff_empty_inputs_produce_empty_report() -> None:
    report = diff_against_audit(_figma_with(), _audit_payload())
    assert report.summary_counts == {
        "matched": 0,
        "unused_in_code": 0,
        "missing_from_figma": 0,
    }
