"""Tests for lumo-spec (Phase 1 — Markdown source + LLM round-trip).

All LLM-touching tests use a FakeCaller or the ReplayCaller — no network, no
API key. Live recording is out of band (LUMO_TEST_LIVE), not part of CI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from lumo.spec.check import run_check
from lumo.spec.cli import _infer_source_from_url, _resolve_source, main
from lumo.spec.layout import LayoutError, elements_count, layout_source, load_layout
from lumo.spec.llm import (
    EMIT_FINDINGS_TOOL,
    LLMResult,
    build_user_message,
    run_llm,
)
from lumo.spec.models import SpecDocument
from lumo.spec.output import to_json_dict
from lumo.spec.replay import RecordingCaller, ReplayCaller
from lumo.spec.sources import SourceError, get_source
from lumo.spec.sources.markdown import MarkdownSource
from lumo.spec.validators import (
    SPEC_CHAR_CAP,
    SpecTooLongError,
    coerce_findings,
    enforce_length_cap,
    validate_evidence,
)


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #

SPEC_TEXT = """\
# Registration — step 1

The form contains exactly three fields: full name, email, and phone number.
User can return to the previous step at any time via a back arrow in the top-left.
The Continue button only becomes visible once all required fields are filled.
"""

LAYOUT: dict[str, Any] = {
    "screen": {"width": 411, "height": 891, "unit": "dp"},
    "source": "measured",
    "elements": [
        {"id": "field_name", "role": "input", "x": 24, "y": 100, "w": 363, "h": 56},
        {"id": "field_email", "role": "input", "x": 24, "y": 170, "w": 363, "h": 56},
        {"id": "field_phone", "role": "input", "x": 24, "y": 240, "w": 363, "h": 56},
        {"id": "field_extra1", "role": "input", "x": 24, "y": 310, "w": 363, "h": 56},
        {"id": "field_extra2", "role": "input", "x": 24, "y": 380, "w": 363, "h": 56},
        {"id": "btn_continue", "role": "primary_action", "x": 24, "y": 800, "w": 363, "h": 56},
    ],
}


class FakeCaller:
    """Returns a fixed findings list, recording what it was asked."""

    def __init__(self, findings: list[dict[str, Any]], *, raises: int = 0) -> None:
        self._findings = findings
        self._raises = raises
        self.calls: list[tuple[list[dict[str, Any]], str, str]] = []

    def call(self, system: list[dict[str, Any]], user: str, model: str) -> LLMResult:
        self.calls.append((system, user, model))
        if self._raises > 0:
            from lumo.spec.llm import LLMError

            self._raises -= 1
            raise LLMError("boom")
        return LLMResult(findings=self._findings, input_tokens=120, output_tokens=80)


def _doc(text: str = SPEC_TEXT) -> SpecDocument:
    return SpecDocument(
        source_type="markdown",
        source_id="prd.md",
        title="Registration — step 1",
        markdown=text,
        fetched_at=datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc),
    )


GOOD_FINDING = {
    "id": "element_count_mismatch",
    "severity": "medium",
    "confidence": "high",
    "element": None,
    "message": "Spec calls for 3 input fields; layout has 5.",
    "evidence": "The form contains exactly three fields: full name, email, and phone number.",
    "recommendation": "Remove the two extra fields or confirm the spec is current.",
}


# --------------------------------------------------------------------------- #
# Markdown source
# --------------------------------------------------------------------------- #

def test_markdown_source_reads_file_and_extracts_h1_title(tmp_path: Path) -> None:
    p = tmp_path / "prd.md"
    p.write_text(SPEC_TEXT, encoding="utf-8")
    doc = MarkdownSource().fetch(str(p))
    assert doc.source_type == "markdown"
    assert doc.title == "Registration — step 1"
    assert doc.markdown == SPEC_TEXT
    assert doc.character_count == len(SPEC_TEXT)


def test_markdown_source_falls_back_to_filename_when_no_h1(tmp_path: Path) -> None:
    p = tmp_path / "notes.md"
    p.write_text("no heading here\n", encoding="utf-8")
    doc = MarkdownSource().fetch(str(p))
    assert doc.title == "notes.md"


def test_markdown_source_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        MarkdownSource().fetch("/nope/does-not-exist.md")


def test_get_source_unknown_raises() -> None:
    with pytest.raises(SourceError):
        get_source("notion")


# --------------------------------------------------------------------------- #
# Layout loading
# --------------------------------------------------------------------------- #

def test_load_layout_defaults_source(tmp_path: Path) -> None:
    p = tmp_path / "l.json"
    p.write_text(json.dumps({"elements": []}), encoding="utf-8")
    data = load_layout(str(p))
    assert data["source"] == "description-estimated"
    assert elements_count(data) == 0


def test_load_layout_preserves_explicit_source() -> None:
    assert layout_source(LAYOUT) == "measured"
    assert elements_count(LAYOUT) == 6


def test_load_layout_rejects_non_object(tmp_path: Path) -> None:
    p = tmp_path / "l.json"
    p.write_text("[1,2,3]", encoding="utf-8")
    with pytest.raises(LayoutError):
        load_layout(str(p))


def test_load_layout_rejects_missing_elements(tmp_path: Path) -> None:
    p = tmp_path / "l.json"
    p.write_text(json.dumps({"screen": {}}), encoding="utf-8")
    with pytest.raises(LayoutError):
        load_layout(str(p))


# --------------------------------------------------------------------------- #
# Length cap — honesty rule 7
# --------------------------------------------------------------------------- #

def test_length_cap_passes_under() -> None:
    enforce_length_cap("x" * 10, cap=100)  # no raise


def test_length_cap_fails_fast_over() -> None:
    with pytest.raises(SpecTooLongError) as ei:
        enforce_length_cap("x" * 101, cap=100)
    # error must report the real count and never claim truncation happened
    assert "101" in str(ei.value)
    assert "NOT truncated" in str(ei.value)


def test_default_cap_is_a_placeholder_value() -> None:
    assert SPEC_CHAR_CAP == 32_000


# --------------------------------------------------------------------------- #
# Evidence-substring validator — honesty rule 3
# --------------------------------------------------------------------------- #

def test_evidence_validator_keeps_real_quote() -> None:
    findings, _ = coerce_findings([GOOD_FINDING])
    kept, dropped = validate_evidence(findings, SPEC_TEXT)
    assert len(kept) == 1
    assert dropped == 0


def test_evidence_validator_drops_fabricated_quote(capsys: pytest.CaptureFixture) -> None:
    fake = dict(GOOD_FINDING, evidence="The spec demands a fingerprint scanner.")
    findings, _ = coerce_findings([fake])
    kept, dropped = validate_evidence(findings, SPEC_TEXT)
    assert kept == []
    assert dropped == 1
    assert "fabricated evidence" in capsys.readouterr().err


def test_evidence_validator_tolerates_whitespace_rewrap() -> None:
    # quote with collapsed internal whitespace still matches
    fake = dict(GOOD_FINDING, evidence="The form  contains   exactly three fields")
    findings, _ = coerce_findings([fake])
    kept, dropped = validate_evidence(findings, SPEC_TEXT)
    assert len(kept) == 1
    assert dropped == 0


def test_evidence_validator_drops_empty_quote() -> None:
    fake = dict(GOOD_FINDING, evidence="   ")
    findings, _ = coerce_findings([fake])
    kept, dropped = validate_evidence(findings, SPEC_TEXT)
    assert kept == []
    assert dropped == 1


# --------------------------------------------------------------------------- #
# Schema coercion — defends the locked enums
# --------------------------------------------------------------------------- #

def test_coerce_drops_unknown_id(capsys: pytest.CaptureFixture) -> None:
    bad = dict(GOOD_FINDING, id="totally_made_up")
    findings, dropped = coerce_findings([bad])
    assert findings == []
    assert dropped == 1
    assert "schema violation" in capsys.readouterr().err


def test_coerce_drops_bad_severity() -> None:
    bad = dict(GOOD_FINDING, severity="catastrophic")
    findings, dropped = coerce_findings([bad])
    assert findings == [] and dropped == 1


def test_coerce_accepts_valid() -> None:
    findings, dropped = coerce_findings([GOOD_FINDING])
    assert len(findings) == 1 and dropped == 0
    assert findings[0].id == "element_count_mismatch"


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #

def test_run_check_happy_path_one_finding() -> None:
    caller = FakeCaller([GOOD_FINDING])
    report = run_check(spec=_doc(), layout=LAYOUT, caller=caller, model="m")
    assert len(report.findings) == 1
    assert report.findings[0].id == "element_count_mismatch"
    assert report.layout_elements_count == 6
    assert report.layout_source == "measured"
    assert report.input_tokens == 120


def test_run_check_zero_findings_when_satisfied() -> None:
    caller = FakeCaller([])
    report = run_check(spec=_doc(), layout=LAYOUT, caller=caller, model="m")
    assert report.findings == ()


def test_run_check_sorts_by_severity() -> None:
    low = dict(GOOD_FINDING, id="extraneous_element", severity="low")
    high = dict(GOOD_FINDING, id="missing_required_element", severity="high",
                evidence="User can return to the previous step at any time via a back arrow in the top-left.")
    caller = FakeCaller([low, high])
    report = run_check(spec=_doc(), layout=LAYOUT, caller=caller, model="m")
    assert [f.severity for f in report.findings] == ["high", "low"]


def test_run_check_severity_floor() -> None:
    low = dict(GOOD_FINDING, id="extraneous_element", severity="low")
    caller = FakeCaller([GOOD_FINDING, low])  # medium + low
    report = run_check(
        spec=_doc(), layout=LAYOUT, caller=caller, model="m", severity_floor="medium"
    )
    assert all(f.severity in ("high", "medium") for f in report.findings)
    assert len(report.findings) == 1


def test_run_check_fabricated_evidence_counted() -> None:
    fake = dict(GOOD_FINDING, evidence="not in the spec at all")
    caller = FakeCaller([GOOD_FINDING, fake])
    report = run_check(spec=_doc(), layout=LAYOUT, caller=caller, model="m")
    assert len(report.findings) == 1
    assert report.dropped_fabricated == 1


def test_run_check_over_cap_raises() -> None:
    big = _doc("x" * 50_000)
    caller = FakeCaller([])
    with pytest.raises(SpecTooLongError):
        run_check(spec=big, layout=LAYOUT, caller=caller, model="m")


# --------------------------------------------------------------------------- #
# LLM layer — retry + prompt shape
# --------------------------------------------------------------------------- #

def test_run_llm_retries_once_then_succeeds() -> None:
    caller = FakeCaller([GOOD_FINDING], raises=1)
    result = run_llm(caller=caller, spec_markdown=SPEC_TEXT, layout=LAYOUT, model="m")
    assert len(result.findings) == 1
    assert len(caller.calls) == 2  # one failure + one success


def test_run_llm_raises_after_two_failures() -> None:
    from lumo.spec.llm import LLMError

    caller = FakeCaller([], raises=2)
    with pytest.raises(LLMError):
        run_llm(caller=caller, spec_markdown=SPEC_TEXT, layout=LAYOUT, model="m")


def test_system_prompt_is_cache_marked() -> None:
    caller = FakeCaller([])
    run_llm(caller=caller, spec_markdown=SPEC_TEXT, layout=LAYOUT, model="m")
    system, _user, _model = caller.calls[0]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_user_message_wraps_spec_and_layout() -> None:
    msg = build_user_message(SPEC_TEXT, LAYOUT)
    assert "<spec>" in msg and "</spec>" in msg
    assert "<layout>" in msg and "btn_continue" in msg


def test_tool_schema_enum_is_locked() -> None:
    props = EMIT_FINDINGS_TOOL["input_schema"]["properties"]["findings"]["items"]["properties"]
    assert "ambiguous_requirement" in props["id"]["enum"]
    assert props["severity"]["enum"] == ["high", "medium", "low"]


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def test_json_envelope_shape() -> None:
    caller = FakeCaller([GOOD_FINDING])
    report = run_check(spec=_doc(), layout=LAYOUT, caller=caller, model="claude-haiku-4-5-20251001")
    d = to_json_dict(report)
    assert d["tool"] == "lumo-spec"
    assert d["source"] == "llm-derived"  # honesty rule 1
    assert d["model"] == "claude-haiku-4-5-20251001"
    assert d["spec"]["fetched_at"].endswith("Z")
    assert d["summary"]["total"] == 1
    assert d["summary"]["by_severity"]["medium"] == 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_url_inference_confluence() -> None:
    src, ident = _infer_source_from_url(
        "https://acme.atlassian.net/wiki/spaces/MOB/pages/123456789/Reg"
    )
    assert src == "confluence" and ident == "123456789"


def test_url_inference_jira() -> None:
    src, ident = _infer_source_from_url("https://acme.atlassian.net/browse/APP-1234")
    assert src == "jira" and ident == "APP-1234"


def test_url_inference_unknown_raises() -> None:
    with pytest.raises(SourceError):
        _infer_source_from_url("https://example.com/whatever")


def test_resolve_source_infers_markdown_from_spec(tmp_path: Path) -> None:
    args = type("A", (), {"url": None, "source": None, "spec": "x.md",
                          "page_id": None, "issue_key": None})()
    assert _resolve_source(args) == ("markdown", "x.md")


def test_cli_markdown_with_findings_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    spec = tmp_path / "prd.md"
    spec.write_text(SPEC_TEXT, encoding="utf-8")
    layout = tmp_path / "screen.json"
    layout.write_text(json.dumps(LAYOUT), encoding="utf-8")

    rc = main(["check", "--layout", str(layout), "--spec", str(spec)],
              caller=FakeCaller([GOOD_FINDING]))
    assert rc == 1
    out = capsys.readouterr().out
    assert "FOUND  1 findings" in out


def test_cli_markdown_clean_exits_0(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    spec = tmp_path / "prd.md"
    spec.write_text(SPEC_TEXT, encoding="utf-8")
    layout = tmp_path / "screen.json"
    layout.write_text(json.dumps(LAYOUT), encoding="utf-8")

    rc = main(["check", "--layout", str(layout), "--spec", str(spec)],
              caller=FakeCaller([]))
    assert rc == 0
    assert "no spec-vs-layout findings" in capsys.readouterr().out


def test_cli_json_and_out_file(tmp_path: Path) -> None:
    spec = tmp_path / "prd.md"
    spec.write_text(SPEC_TEXT, encoding="utf-8")
    layout = tmp_path / "screen.json"
    layout.write_text(json.dumps(LAYOUT), encoding="utf-8")
    out = tmp_path / "findings.json"

    rc = main(
        ["check", "--layout", str(layout), "--spec", str(spec), "--json", "--out", str(out)],
        caller=FakeCaller([GOOD_FINDING]),
    )
    assert rc == 1
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["tool"] == "lumo-spec"


def test_cli_unshipped_source_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    layout = tmp_path / "screen.json"
    layout.write_text(json.dumps(LAYOUT), encoding="utf-8")
    rc = main(["check", "--layout", str(layout), "--source", "jira", "--issue-key", "APP-1"])
    assert rc == 2
    assert "not in this build yet" in capsys.readouterr().err


def test_cli_missing_source_exits_2(tmp_path: Path) -> None:
    layout = tmp_path / "screen.json"
    layout.write_text(json.dumps(LAYOUT), encoding="utf-8")
    rc = main(["check", "--layout", str(layout)])
    assert rc == 2


def test_cli_over_cap_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    spec = tmp_path / "prd.md"
    spec.write_text("x" * 50_000, encoding="utf-8")
    layout = tmp_path / "screen.json"
    layout.write_text(json.dumps(LAYOUT), encoding="utf-8")
    rc = main(["check", "--layout", str(layout), "--spec", str(spec)], caller=FakeCaller([]))
    assert rc == 2
    assert "over the" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Replay shim
# --------------------------------------------------------------------------- #

def test_record_then_replay_round_trip(tmp_path: Path) -> None:
    cassette = tmp_path / "cassette.jsonl"
    recorder = RecordingCaller(FakeCaller([GOOD_FINDING]), cassette)
    # record
    report1 = run_check(spec=_doc(), layout=LAYOUT, caller=recorder, model="m")
    # replay — no live caller involved
    replayer = ReplayCaller(cassette)
    report2 = run_check(spec=_doc(), layout=LAYOUT, caller=replayer, model="m")
    assert [f.id for f in report1.findings] == [f.id for f in report2.findings]


def test_replay_miss_raises(tmp_path: Path) -> None:
    from lumo.spec.llm import LLMError

    cassette = tmp_path / "empty.jsonl"
    cassette.write_text("", encoding="utf-8")
    replayer = ReplayCaller(cassette)
    with pytest.raises(LLMError):
        run_check(spec=_doc(), layout=LAYOUT, caller=replayer, model="m")
