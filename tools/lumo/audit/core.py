"""Whole-repository audit aggregator.

The per-file `lumo.source.check_*` tools answer "what's wrong with this
file". This module answers two questions a per-file run cannot:

  1. Where are the drift hotspots? — aggregate findings across the repo,
     grouped by check, file, and category.

  2. What is the project's *measured* spacing / radius scale? — count
     every hardcoded numeric literal and surface the top values. Compare
     against the configured scale to see actual drift, not just rule
     violations on individual lines.

We never auto-propose changes — Lumo surfaces data, the human decides
what to keep. Token references stay invisible per the honesty rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lumo.source.core import (
    DEFAULT_RADIUS_SCALE_DP,
    DEFAULT_SPACING_SCALE_DP,
    LiteralValue,
    SourceFinding,
    SourceReport,
    check_compose,
    check_swiftui,
    iter_compose_literals,
    iter_swiftui_literals,
)

Language = Literal["kotlin", "swift"]

# Directories the audit walker always skips. These are output / vendored
# trees that would produce thousands of false matches and slow the scan
# without adding signal. The user can extend this list via the config's
# `exclude` field; they cannot shrink it — those directories never carry
# hand-written design code.
DEFAULT_SKIP_DIRS: tuple[str, ...] = (
    ".git",
    ".gradle",
    ".idea",
    "build",
    "Pods",
    "DerivedData",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "out",
)


# ============================================================================
# Config + report dataclasses
# ============================================================================


@dataclass(frozen=True)
class AuditConfig:
    """How to walk the repo and what scale to compare against.

    The defaults are intentionally permissive: scan everything under
    `root`, use the Material / HIG spacing scale, no extra excludes.
    Override by reading `lumo.config.json`'s `audit:` section in the CLI.
    """

    spacing_scale: tuple[float, ...] = DEFAULT_SPACING_SCALE_DP
    radius_scale: tuple[float, ...] = DEFAULT_RADIUS_SCALE_DP
    # Additional glob patterns to exclude, on top of DEFAULT_SKIP_DIRS.
    # Globs are matched against POSIX-style paths relative to `root`.
    extra_excludes: tuple[str, ...] = ()
    # How many top values to surface per scale-observation table.
    top_n_values: int = 15


@dataclass(frozen=True)
class ScaleObservation:
    """Frequency table of literal values for one scale category.

    `kind` is `"padding"`, `"radius"`, or `"size"`. `values_by_frequency`
    is `[(value, count), ...]` sorted by count desc, value asc. The
    `on_scale` / `off_scale` partitions are computed against the
    configured scale at audit time.
    """

    kind: Literal["padding", "radius", "size"]
    values_by_frequency: tuple[tuple[float, int], ...]
    on_scale: tuple[float, ...]
    off_scale: tuple[float, ...]
    total_literals: int


@dataclass(frozen=True)
class AuditReport:
    """The output of `scan_repo`."""

    root: str
    files_scanned: int
    files_with_findings: int
    findings: tuple[SourceFinding, ...]
    counts_by_check: dict[str, int] = field(default_factory=dict)
    counts_by_category: dict[str, int] = field(default_factory=dict)
    counts_by_severity: dict[str, int] = field(default_factory=dict)
    counts_by_language: dict[Language, int] = field(default_factory=dict)
    scale_observations: tuple[ScaleObservation, ...] = ()

    @property
    def total_findings(self) -> int:
        return len(self.findings)


# ============================================================================
# File walking
# ============================================================================


def _iter_source_files(
    root: Path, extra_excludes: tuple[str, ...]
) -> list[tuple[Path, Language]]:
    """Walk `root` and return every `.kt` / `.swift` file we should check."""
    import fnmatch

    results: list[tuple[Path, Language]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # Hard-coded skip: any path segment matches DEFAULT_SKIP_DIRS.
        if any(part in DEFAULT_SKIP_DIRS for part in path.parts):
            continue
        # Extra excludes (POSIX-style globs relative to root).
        rel = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(rel, pat) for pat in extra_excludes):
            continue
        suffix = path.suffix.lower()
        if suffix in (".kt", ".kts"):
            results.append((path, "kotlin"))
        elif suffix == ".swift":
            results.append((path, "swift"))
    results.sort()
    return results


# ============================================================================
# Scale-observation aggregation
# ============================================================================


def _aggregate_literals(
    literals: list[LiteralValue],
    spacing_scale: tuple[float, ...],
    radius_scale: tuple[float, ...],
    top_n: int,
) -> tuple[ScaleObservation, ...]:
    """Bucket literals by kind, count by value, partition on/off scale."""
    by_kind: dict[str, list[float]] = {"padding": [], "radius": [], "size": []}
    for lit in literals:
        by_kind[lit.kind].append(lit.value)

    observations: list[ScaleObservation] = []
    for kind in ("padding", "radius", "size"):
        values = by_kind[kind]
        if not values:
            continue
        scale = radius_scale if kind == "radius" else spacing_scale
        counter = Counter(values)
        ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
        on_scale = sorted({v for v in values if v in scale})
        off_scale = sorted({v for v in values if v not in scale})
        kind_typed: Literal["padding", "radius", "size"]
        if kind == "padding":
            kind_typed = "padding"
        elif kind == "radius":
            kind_typed = "radius"
        else:
            kind_typed = "size"
        observations.append(
            ScaleObservation(
                kind=kind_typed,
                values_by_frequency=tuple(ranked),
                on_scale=tuple(on_scale),
                off_scale=tuple(off_scale),
                total_literals=len(values),
            )
        )
    return tuple(observations)


# ============================================================================
# Entry point
# ============================================================================


def scan_repo(root: str | Path, config: AuditConfig | None = None) -> AuditReport:
    """Walk `root`, run lumo.source checks, aggregate findings + scale data.

    Returns a single `AuditReport`. Token references are never counted —
    the honesty rule from `lumo.source` is preserved end-to-end.
    """
    cfg = config or AuditConfig()
    root_path = Path(root).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise NotADirectoryError(f"audit root does not exist or is not a directory: {root_path}")

    files = _iter_source_files(root_path, cfg.extra_excludes)

    all_findings: list[SourceFinding] = []
    files_with_findings = 0
    counts_by_language: dict[Language, int] = {"kotlin": 0, "swift": 0}
    literals: list[LiteralValue] = []

    for path, lang in files:
        counts_by_language[lang] += 1
        source = path.read_text(encoding="utf-8", errors="replace")
        rel_path = path.relative_to(root_path).as_posix()
        if lang == "kotlin":
            report: SourceReport = check_compose(
                source,
                path=rel_path,
                spacing_scale=cfg.spacing_scale,
                radius_scale=cfg.radius_scale,
            )
            literals.extend(iter_compose_literals(source, path=rel_path))
        else:
            report = check_swiftui(
                source,
                path=rel_path,
                spacing_scale=cfg.spacing_scale,
                radius_scale=cfg.radius_scale,
            )
            literals.extend(iter_swiftui_literals(source, path=rel_path))

        if report.findings:
            files_with_findings += 1
        all_findings.extend(report.findings)

    # Aggregate counts.
    counts_by_check: Counter[str] = Counter(f.check for f in all_findings)
    counts_by_category: Counter[str] = Counter(f.category for f in all_findings)
    counts_by_severity: Counter[str] = Counter(f.severity for f in all_findings)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    all_findings.sort(key=lambda f: (severity_order[f.severity], f.file, f.line))

    observations = _aggregate_literals(
        literals,
        cfg.spacing_scale,
        cfg.radius_scale,
        cfg.top_n_values,
    )

    return AuditReport(
        root=str(root_path),
        files_scanned=len(files),
        files_with_findings=files_with_findings,
        findings=tuple(all_findings),
        counts_by_check=dict(counts_by_check),
        counts_by_category=dict(counts_by_category),
        counts_by_severity=dict(counts_by_severity),
        counts_by_language={k: v for k, v in counts_by_language.items() if v > 0},
        scale_observations=observations,
    )
