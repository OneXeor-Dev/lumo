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


# ============================================================================
# Figma layout render (0.2.0)
# ============================================================================

from lumo.figma.core import (  # noqa: E402
    _parse_node_layout_payload,
    fetch_node_layout,
)


def _figma_nodes_payload(
    node_id: str,
    *,
    frame_w: float = 411,
    frame_h: float = 891,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal Figma /v1/files/.../nodes response."""
    return {
        "nodes": {
            node_id: {
                "document": {
                    "id": node_id,
                    "name": "Login Screen",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": frame_w, "height": frame_h},
                    "children": children or [],
                }
            }
        }
    }


def test_render_emits_measured_source_on_every_element() -> None:
    payload = _figma_nodes_payload(
        "1:23",
        children=[
            {"id": "1:24", "name": "Title", "type": "TEXT",
             "absoluteBoundingBox": {"x": 24, "y": 80, "width": 363, "height": 32}},
        ],
    )
    report = _parse_node_layout_payload(payload, "1:23")
    assert all(e.source == "measured" for e in report.elements)


def test_render_coordinates_are_relative_to_root_frame() -> None:
    payload = _figma_nodes_payload(
        "1:23",
        children=[
            {"id": "1:24", "name": "Title", "type": "TEXT",
             "absoluteBoundingBox": {"x": 24, "y": 80, "width": 363, "height": 32}},
        ],
    )
    # Root frame is at (0,0) — child should keep its 24/80.
    report = _parse_node_layout_payload(payload, "1:23")
    title = report.elements[0]
    assert title.x == 24.0
    assert title.y == 80.0


def test_render_translates_when_root_is_not_at_origin() -> None:
    # Figma artboards can sit anywhere on the canvas — child coords
    # are still in global space and must be normalised.
    payload = {
        "nodes": {"5:1": {"document": {
            "id": "5:1", "name": "Frame", "type": "FRAME",
            "absoluteBoundingBox": {"x": 500, "y": 200, "width": 360, "height": 800},
            "children": [
                {"id": "5:2", "name": "btn_continue", "type": "INSTANCE",
                 "absoluteBoundingBox": {"x": 516, "y": 280, "width": 328, "height": 56}},
            ],
        }}}
    }
    report = _parse_node_layout_payload(payload, "5:1")
    btn = report.elements[0]
    # 516 - 500 = 16, 280 - 200 = 80
    assert btn.x == 16.0
    assert btn.y == 80.0


def test_render_role_heuristic_button() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "btn_continue", "type": "INSTANCE",
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 56}},
    ])
    e = _parse_node_layout_payload(payload, "1:23").elements[0]
    assert e.role == "primary_action"


def test_render_role_heuristic_text() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "Welcome", "type": "TEXT",
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 24}},
    ])
    e = _parse_node_layout_payload(payload, "1:23").elements[0]
    assert e.role == "text"


def test_render_role_heuristic_icon_square_vector() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "chevron", "type": "VECTOR",
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 24, "height": 24}},
    ])
    e = _parse_node_layout_payload(payload, "1:23").elements[0]
    assert e.role == "icon"


def test_render_role_heuristic_input_prefix() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "input_email", "type": "FRAME",
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 343, "height": 48}},
    ])
    e = _parse_node_layout_payload(payload, "1:23").elements[0]
    assert e.role == "input"


def test_render_role_heuristic_decorative_fallback() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "background_blob", "type": "GROUP",
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 200, "height": 200}},
    ])
    e = _parse_node_layout_payload(payload, "1:23").elements[0]
    assert e.role == "decorative"


def test_render_sanitises_layer_name_to_element_id() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "Btn / Continue", "type": "INSTANCE",
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 56}},
    ])
    e = _parse_node_layout_payload(payload, "1:23").elements[0]
    assert e.id == "btn_continue"


def test_render_id_collisions_get_suffix() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "Item", "type": "FRAME",
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 56}},
        {"id": "1:25", "name": "Item", "type": "FRAME",
         "absoluteBoundingBox": {"x": 0, "y": 60, "width": 100, "height": 56}},
    ])
    report = _parse_node_layout_payload(payload, "1:23")
    ids = [e.id for e in report.elements]
    assert ids[0] == "item"
    assert ids[1] == "item_2"


def test_render_skips_hidden_layers() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "Visible", "type": "TEXT", "visible": True,
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 20}},
        {"id": "1:25", "name": "Hidden", "type": "TEXT", "visible": False,
         "absoluteBoundingBox": {"x": 0, "y": 30, "width": 100, "height": 20}},
    ])
    report = _parse_node_layout_payload(payload, "1:23")
    ids = {e.id for e in report.elements}
    assert "visible" in ids
    assert "hidden" not in ids


def test_render_skips_nodes_with_null_bbox() -> None:
    # Auto-layout placeholders before Figma measures them have null bbox.
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "ok", "type": "TEXT",
         "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 20}},
        {"id": "1:25", "name": "skipme", "type": "FRAME",
         "absoluteBoundingBox": None,
         "children": [
             {"id": "1:26", "name": "inner", "type": "TEXT",
              "absoluteBoundingBox": {"x": 10, "y": 30, "width": 50, "height": 20}},
         ]},
    ])
    report = _parse_node_layout_payload(payload, "1:23")
    ids = {e.id for e in report.elements}
    assert "ok" in ids
    assert "skipme" not in ids
    # We still walk children of a no-bbox node — inner has a real bbox.
    assert "inner" in ids


def test_render_screen_size_falls_back_to_frame_dims() -> None:
    payload = _figma_nodes_payload("1:23", frame_w=393, frame_h=852)
    report = _parse_node_layout_payload(payload, "1:23")
    assert report.screen_width == 393.0
    assert report.screen_height == 852.0


def test_render_screen_size_explicit_override() -> None:
    payload = _figma_nodes_payload("1:23", frame_w=1440, frame_h=900)
    report = _parse_node_layout_payload(
        payload, "1:23", screen_width=411, screen_height=891,
    )
    assert report.screen_width == 411.0
    assert report.screen_height == 891.0


def test_render_raises_on_missing_node_in_response() -> None:
    payload = {"nodes": {}}
    with pytest.raises(FigmaApiError) as exc:
        _parse_node_layout_payload(payload, "9:99")
    assert "9:99" in str(exc.value)


def test_render_raises_on_root_without_bbox() -> None:
    payload = {"nodes": {"1:23": {"document": {
        "id": "1:23", "name": "broken", "type": "FRAME",
        "absoluteBoundingBox": None,
        "children": [],
    }}}}
    with pytest.raises(FigmaApiError) as exc:
        _parse_node_layout_payload(payload, "1:23")
    assert "absoluteBoundingBox" in str(exc.value)


def test_render_group_hint_propagates_to_children() -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "Bottom Nav", "type": "FRAME",
         "absoluteBoundingBox": {"x": 0, "y": 800, "width": 411, "height": 80},
         "children": [
             {"id": "1:25", "name": "nav_home", "type": "INSTANCE",
              "absoluteBoundingBox": {"x": 0, "y": 800, "width": 103, "height": 56}},
         ]},
    ])
    report = _parse_node_layout_payload(payload, "1:23")
    home = next(e for e in report.elements if e.id == "nav_home")
    assert home.group == "bottom_nav"


def test_fetch_node_layout_via_mock_http(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "Title", "type": "TEXT",
         "absoluteBoundingBox": {"x": 24, "y": 80, "width": 363, "height": 32}},
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/files/abc/nodes"
        assert request.url.params["ids"] == "1:23"
        assert request.headers.get("X-Figma-Token") == "tok"
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    monkeypatch.setenv("FIGMA_TOKEN", "tok")
    report = fetch_node_layout("abc", "1:23", http_client=client)
    assert report.screen_width == 411.0
    assert report.elements[0].id == "title"


# ============================================================================
# MCP wrapper for figma render
# ============================================================================


def test_mcp_figma_render_wrapper_matches_direct_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    server_module = sys.modules["lumo.mcp.server"]
    payload = _figma_nodes_payload("1:23", children=[
        {"id": "1:24", "name": "btn_login", "type": "INSTANCE",
         "absoluteBoundingBox": {"x": 24, "y": 800, "width": 363, "height": 56}},
    ])
    monkeypatch.setattr(
        server_module,
        "figma_fetch_node_layout",
        lambda fk, nid, screen_width=None, screen_height=None: _parse_node_layout_payload(
            payload, nid, screen_width=screen_width, screen_height=screen_height,
        ),
    )
    out = server_module.lumo_figma_render(file_key="abc", node_id="1:23")
    assert out["screen"]["width"] == 411
    assert out["elements"][0]["id"] == "btn_login"
    assert out["elements"][0]["role"] == "primary_action"
    assert out["elements"][0]["source"] == "measured"


def test_mcp_figma_render_normalises_node_id_dash_to_colon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    server_module = sys.modules["lumo.mcp.server"]
    seen_ids: list[str] = []
    payload = _figma_nodes_payload("1:23", children=[])

    def fake(file_key: str, node_id: str, *, screen_width=None, screen_height=None):
        seen_ids.append(node_id)
        return _parse_node_layout_payload(payload, node_id)

    monkeypatch.setattr(server_module, "figma_fetch_node_layout", fake)
    server_module.lumo_figma_render(file_key="abc", node_id="1-23")
    assert seen_ids == ["1:23"]
