"""Tests for lumo.audit — whole-repo aggregation.

Each test builds a tiny in-memory repo under pytest's `tmp_path` fixture
and runs `scan_repo` against it. Positive cases assert specific
aggregations (file counts, finding counts, scale-observation values).
Negative cases assert clean repos produce empty reports.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lumo.audit.core import (
    DEFAULT_SKIP_DIRS,
    AuditConfig,
    AuditReport,
    ScaleObservation,
    scan_repo,
)


# ============================================================================
# Helpers
# ============================================================================


def _write(root: Path, rel: str, content: str) -> Path:
    """Write a file inside `root`, creating parents as needed."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _obs(report: AuditReport, kind: str) -> ScaleObservation | None:
    for obs in report.scale_observations:
        if obs.kind == kind:
            return obs
    return None


# ============================================================================
# Walking + filtering
# ============================================================================


def test_empty_root_produces_empty_report(tmp_path: Path) -> None:
    report = scan_repo(tmp_path)
    assert report.files_scanned == 0
    assert report.total_findings == 0
    assert report.scale_observations == ()
    assert report.counts_by_language == {}


def test_invalid_root_raises(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        scan_repo(tmp_path / "does-not-exist")


def test_walker_picks_up_kt_and_swift_files(tmp_path: Path) -> None:
    _write(tmp_path, "src/a.kt", "")
    _write(tmp_path, "src/b.swift", "")
    _write(tmp_path, "src/c.txt", "ignored")  # not a source file
    _write(tmp_path, "src/d.py", "ignored")
    report = scan_repo(tmp_path)
    assert report.files_scanned == 2
    assert report.counts_by_language == {"kotlin": 1, "swift": 1}


def test_walker_skips_default_directories(tmp_path: Path) -> None:
    # All these paths should be invisible to the scan.
    for skipped in DEFAULT_SKIP_DIRS:
        _write(tmp_path, f"{skipped}/inside.kt", "")
    _write(tmp_path, "src/visible.kt", "")
    report = scan_repo(tmp_path)
    assert report.files_scanned == 1


def test_walker_respects_extra_excludes(tmp_path: Path) -> None:
    _write(tmp_path, "src/keep.kt", "")
    _write(tmp_path, "tests/skip.kt", "")
    _write(tmp_path, "samples/skip.kt", "")
    report = scan_repo(
        tmp_path,
        AuditConfig(extra_excludes=("tests/**", "samples/**")),
    )
    assert report.files_scanned == 1


# ============================================================================
# Finding aggregation
# ============================================================================


_BAD_COMPOSE = """
@Composable
fun Bad() {
    IconButton(onClick = {}, modifier = Modifier.size(32.dp)) { }
    Surface(color = Color(0xFFAA0000)) { }
}
"""

_BAD_SWIFTUI = """
struct Bad: View {
    var body: some View {
        Button(action: {}) { }.frame(width: 20, height: 20)
        Rectangle().cornerRadius(13)
    }
}
"""

_CLEAN_COMPOSE = """
@Composable
fun Clean() {
    IconButton(onClick = {}, modifier = Modifier.size(48.dp)) { }
    Surface(color = MaterialTheme.colorScheme.primary) { }
}
"""


def test_aggregates_findings_across_files(tmp_path: Path) -> None:
    _write(tmp_path, "feature/a/Bad.kt", _BAD_COMPOSE)
    _write(tmp_path, "feature/b/Bad.swift", _BAD_SWIFTUI)
    _write(tmp_path, "feature/c/Clean.kt", _CLEAN_COMPOSE)
    report = scan_repo(tmp_path)

    assert report.files_scanned == 3
    assert report.files_with_findings == 2
    # Compose: 1 undersized + 1 hardcoded_color. SwiftUI: 1 undersized + 1
    # off_scale_radius. Clean.kt: nothing.
    assert report.total_findings == 4

    assert report.counts_by_check.get("undersized_tap_target") == 2
    assert report.counts_by_check.get("hardcoded_color") == 1
    assert report.counts_by_check.get("off_scale_radius") == 1


def test_findings_carry_path_relative_to_root(tmp_path: Path) -> None:
    _write(tmp_path, "feature/Bad.kt", _BAD_COMPOSE)
    report = scan_repo(tmp_path)
    for f in report.findings:
        # POSIX-style relative path, not absolute.
        assert not f.file.startswith("/")
        assert "feature/Bad.kt" in f.file


def test_clean_repo_yields_zero_findings(tmp_path: Path) -> None:
    _write(tmp_path, "Clean.kt", _CLEAN_COMPOSE)
    report = scan_repo(tmp_path)
    assert report.total_findings == 0
    assert report.files_with_findings == 0


# ============================================================================
# Scale observation
# ============================================================================


def test_scale_observation_counts_literals_across_files(tmp_path: Path) -> None:
    # Three files, each padding(16.dp). One file has padding(13.dp).
    _write(tmp_path, "a.kt", "@Composable fun A() { Column(modifier = Modifier.padding(16.dp)) {} }")
    _write(tmp_path, "b.kt", "@Composable fun B() { Column(modifier = Modifier.padding(16.dp)) {} }")
    _write(tmp_path, "c.kt", "@Composable fun C() { Column(modifier = Modifier.padding(16.dp)) {} }")
    _write(tmp_path, "d.kt", "@Composable fun D() { Column(modifier = Modifier.padding(13.dp)) {} }")
    report = scan_repo(tmp_path)

    obs = _obs(report, "padding")
    assert obs is not None
    assert obs.total_literals == 4
    # 16 should be the most frequent, then 13.
    assert obs.values_by_frequency[0] == (16.0, 3)
    assert obs.values_by_frequency[1] == (13.0, 1)
    # 16 is on default scale, 13 is not.
    assert 16.0 in obs.on_scale
    assert 13.0 in obs.off_scale


def test_scale_observation_ignores_token_references(tmp_path: Path) -> None:
    # `MaterialTheme.spacing.md.dp` MUST NOT be counted — only literals.
    _write(
        tmp_path,
        "Themed.kt",
        """
        @Composable
        fun Themed() {
            Column(modifier = Modifier.padding(MaterialTheme.spacing.md)) {}
            Column(modifier = Modifier.padding(16.dp)) {}
        }
        """,
    )
    report = scan_repo(tmp_path)
    obs = _obs(report, "padding")
    assert obs is not None
    # Exactly one literal — the MaterialTheme reference is skipped.
    assert obs.total_literals == 1


def test_scale_observation_swiftui_uses_pt_literals(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Box.swift",
        """
        struct Box: View {
            var body: some View {
                Text("a").padding(16)
                Text("b").padding(.horizontal, 13)
                Text("c").padding(Theme.spacing.md)   // token — must NOT count
            }
        }
        """,
    )
    report = scan_repo(tmp_path)
    obs = _obs(report, "padding")
    assert obs is not None
    assert obs.total_literals == 2  # 16 and 13; token skipped


def test_scale_observation_radius_bucket_uses_radius_scale(tmp_path: Path) -> None:
    # 13 is off the default radius scale, 12 is on it.
    _write(
        tmp_path,
        "Cards.swift",
        """
        struct A: View { var body: some View { Rectangle().cornerRadius(12) } }
        struct B: View { var body: some View { Rectangle().cornerRadius(13) } }
        """,
    )
    report = scan_repo(tmp_path)
    obs = _obs(report, "radius")
    assert obs is not None
    assert 12.0 in obs.on_scale
    assert 13.0 in obs.off_scale


def test_top_n_caps_the_frequency_table(tmp_path: Path) -> None:
    # Produce 20 distinct padding values; ask for top 5.
    body = "\n".join(
        f"Column(modifier = Modifier.padding({i}.dp)) {{}}" for i in range(20, 40)
    )
    _write(tmp_path, "Many.kt", f"@Composable fun Many() {{ {body} }}")
    report = scan_repo(tmp_path, AuditConfig(top_n_values=5))
    obs = _obs(report, "padding")
    assert obs is not None
    assert len(obs.values_by_frequency) == 5
    # All 20 should still appear in the on/off-scale partition (no cap on that).
    assert len(obs.on_scale) + len(obs.off_scale) == 20


# ============================================================================
# Counts
# ============================================================================


def test_counts_by_severity_match_findings_total(tmp_path: Path) -> None:
    _write(tmp_path, "Bad.kt", _BAD_COMPOSE)
    _write(tmp_path, "Bad.swift", _BAD_SWIFTUI)
    report = scan_repo(tmp_path)
    assert sum(report.counts_by_severity.values()) == report.total_findings
    assert sum(report.counts_by_check.values()) == report.total_findings
    assert sum(report.counts_by_category.values()) == report.total_findings


def test_counts_by_language_only_lists_present_languages(tmp_path: Path) -> None:
    _write(tmp_path, "only.kt", _CLEAN_COMPOSE)
    report = scan_repo(tmp_path)
    assert report.counts_by_language == {"kotlin": 1}
