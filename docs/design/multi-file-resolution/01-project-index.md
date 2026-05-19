# Phase 1 — Project index

**Status:** Draft.
**Goal of this phase:** Given a project root directory, build a
`Name → file path[]` index for every top-level composable / SwiftUI
View. Nothing else.

---

## Input → Output

**Input:**
- `root: Path` — absolute path to the project root the user supplied
  via `--project-root` / `project_root=`.

**Output:**
- A `ProjectIndex` object:

  ```python
  @dataclass(frozen=True)
  class ProjectIndex:
      root: Path
      compose: dict[str, tuple[Path, ...]]   # "SettingsBlock" → (path1.kt,)
      swiftui: dict[str, tuple[Path, ...]]   # "SettingsBlockView" → (path1.swift,)
      build_ms: int                          # walk + scan duration
  ```

  Values are `tuple[Path, ...]` because the same name CAN appear in
  multiple files. Phase 2 picks one per its own search order; this
  phase just records every match.

---

## Algorithm

1. Walk `root` with `os.walk`, in-place prune the same skip set
   already used by `lumo-audit` (`.git`, `build`, `node_modules`,
   `Pods`, `.gradle`, `.idea`, `dist`, `out`, `.claude`, `.cursor`,
   `.vscode`, `.fleet`, `.zed`, `DerivedData`, `__pycache__`).
2. For each `*.kt` / `*.kts` file, scan with a fast regex (no
   tree-sitter for indexing — overkill at this depth):
   ```python
   COMPOSE_DECL_RE = re.compile(
       r"@Composable\s+(?:[a-zA-Z]+\s+)*"
       r"fun\s+([A-Z][A-Za-z0-9_]*)\s*\(",
       re.MULTILINE,
   )
   ```
3. For each `*.swift` file:
   ```python
   SWIFTUI_DECL_RE = re.compile(
       r"struct\s+([A-Z][A-Za-z0-9_]*)\s*:\s*View\b",
       re.MULTILINE,
   )
   ```
4. Accumulate `name → [paths]` maps for each platform.
5. Return the dataclass; do NOT parse bodies yet — that's Phase 3.

The regex approach was chosen over tree-sitter parsing because:
- The index is a name-only map. We do not need the AST yet.
- Real CRDES (1228 `.kt` files, mostly small) walks in <200 ms with
  regex. Tree-sitter parsing the same tree was 4–6× slower in a
  prototype.
- False positives (e.g. `@Composable` in a comment) are filtered by
  Phase 3 when it actually parses the candidate file and validates
  the body exists.

---

## Worked example

```kotlin path=feature/settings/SettingsBlock.kt
package es.card.plazo.settings

import androidx.compose.runtime.Composable

@Composable
fun SettingsBlock(label: String) {
    // body...
}

@Composable
internal fun SettingsBlockHeader() { /* … */ }
```

```kotlin path=feature/settings/SettingsScreen.kt
@Composable
fun SettingsScreen() {
    Column {
        SettingsBlock(label = "Account")
        SettingsBlock(label = "Privacy")
    }
}
```

Expected `ProjectIndex.compose` after walking `feature/`:

```python
{
    "SettingsBlock": (Path("feature/settings/SettingsBlock.kt"),),
    "SettingsBlockHeader": (Path("feature/settings/SettingsBlock.kt"),),
    "SettingsScreen": (Path("feature/settings/SettingsScreen.kt"),),
}
```

Same shape for SwiftUI; the `View` suffix is incidental, not required.

---

## Failure modes

| | Failure | Behaviour |
|---|---|---|
| F1 | `root` does not exist | Raise `NotADirectoryError`. |
| F2 | `root` is a file, not a dir | Raise `NotADirectoryError`. |
| F3 | Same name in N files | Record all N paths in the tuple. Ambiguity resolution is Phase 2's job. |
| F4 | File contains binary garbage in the middle of `.kt` | `read_text(errors="replace")` — regex skips it harmlessly. |
| F5 | Project too big (>50k files) | No special handling in 0.2.0; document as known limitation. Heuristic time estimate: 50k files ≈ 8s. |
| F6 | `@Composable` in a doc comment | Captured by the regex. Phase 3 filters when validating the body exists. |

---

## Test strategy

Synthetic fixture tree under `tests/fixtures/multi_file/projects/`:

```
project_index_basic/
├── a/Foo.kt              (@Composable fun Foo)
├── b/Bar.kt              (@Composable fun Bar)
└── c/Baz.swift           (struct Baz: View)

project_index_ambiguity/
├── a/SettingsBlock.kt    (@Composable fun SettingsBlock)
└── b/SettingsBlock.kt    (@Composable fun SettingsBlock)

project_index_skips/
├── src/Real.kt           (@Composable fun Real)
└── build/Generated.kt    (@Composable fun Generated)  -- must be skipped

project_index_false_positive_in_comment/
└── Doc.kt                (/** @Composable fun Doc */ then noise)
```

Test assertions:
- `project_index_basic`: 2 compose names, 1 swiftui name.
- `project_index_ambiguity`: `SettingsBlock` maps to a tuple of 2 paths.
- `project_index_skips`: only `Real` appears; `Generated` not present.
- `project_index_false_positive_in_comment`: `Doc` appears in the
  index (Phase 1 doesn't validate); Phase 3's test will assert that
  this name comes back `ast-unresolved` because no real body exists.

---

## Public API

```python
# lumo/render/project_index.py (new file)

@dataclass(frozen=True)
class ProjectIndex:
    root: Path
    compose: dict[str, tuple[Path, ...]]
    swiftui: dict[str, tuple[Path, ...]]
    build_ms: int

def build_project_index(root: str | Path) -> ProjectIndex: ...
```

No CLI surface yet — Phase 1 ships behind the public flag,
`lumo-render` still works in single-file mode until Phase 3 wires it
up.

---

## Done-when checklist

- [ ] `ProjectIndex` dataclass + `build_project_index()` function exist
- [ ] DEFAULT_SKIP_DIRS reused from `lumo.audit.core` (single source of truth)
- [ ] Regex constants tested standalone (golden inputs → expected matches)
- [ ] 5 fixtures cover happy path / ambiguity / skips / comment false positive / missing root
- [ ] mypy strict clean
- [ ] CRDES walk benchmark: <500 ms (target), <2 s (hard cap)
