# Phase 2 — Name resolution

**Status:** Draft.
**Goal of this phase:** Given a `ProjectIndex` and an unknown
composable name encountered during render, return the single best-match
file path — or `None` (which surfaces as `ast-unresolved` downstream).

---

## Input → Output

**Input:**
- `index: ProjectIndex` (built by Phase 1).
- `name: str` — the unknown composable / view name that the evaluator
  just hit (e.g. `"SettingsBlock"`).
- `caller_file: Path | None` — the file we are currently rendering
  from. Used to bias the search toward "same-module-first".
- `platform: Literal["compose", "swiftui"]` — which map to query.

**Output:**
- `ResolvedPath | None`:

  ```python
  @dataclass(frozen=True)
  class ResolvedPath:
      path: Path
      ambiguous_alternatives: tuple[Path, ...]   # empty if unique
  ```

`None` means "no candidate" — Phase 3 emits `ast-unresolved` with
`reason = "unknown composable: <name>"` (the same as today).

---

## Search order (numbered, pyright-style)

When `name` has multiple candidates in the index, pick the first match
from this ordered list:

1. **Same directory as `caller_file`.** A composable referenced from
   `ui/profile/ProfileSettingsScreen.kt` is most likely defined in
   another file under `ui/profile/`. If exactly one candidate matches,
   pick it.
2. **Closest common-parent directory.** Walk up from `caller_file`'s
   directory one step at a time. The first level that contains exactly
   one candidate wins. Stops at the `root` of the index.
3. **Lexicographic path sort over all candidates.** When the parent
   walk doesn't disambiguate (or `caller_file` is `None`), sort the
   candidate paths and take the first.

Steps 1–2 model "module locality" — Kotlin / KMP projects keep
composables next to their consumers in 90 % of cases. Step 3 is the
deterministic fallback.

The `ResolvedPath.ambiguous_alternatives` field carries every
non-chosen candidate so the top-level `resolution_stats.ambiguities`
in the render report can surface them.

---

## Worked example

Given this fixture:

```
~/ProjectX/
├── ui/
│   ├── profile/
│   │   ├── ProfileSettingsScreen.kt   (calls SettingsBlock)
│   │   └── SettingsBlock.kt           (@Composable fun SettingsBlock)
│   └── common/
│       └── SettingsBlock.kt           (@Composable fun SettingsBlock)  ← collision
└── feature/
    └── account/
        └── SettingsBlock.kt           (@Composable fun SettingsBlock)  ← collision
```

```python
index = build_project_index(Path("~/ProjectX"))
# index.compose["SettingsBlock"] == (
#     "feature/account/SettingsBlock.kt",
#     "ui/common/SettingsBlock.kt",
#     "ui/profile/SettingsBlock.kt",
# )  — sorted

resolved = resolve_name(
    index,
    name="SettingsBlock",
    caller_file=Path("~/ProjectX/ui/profile/ProfileSettingsScreen.kt"),
    platform="compose",
)
# resolved.path == Path("~/ProjectX/ui/profile/SettingsBlock.kt")  (same-dir)
# resolved.ambiguous_alternatives == (
#     Path("~/ProjectX/feature/account/SettingsBlock.kt"),
#     Path("~/ProjectX/ui/common/SettingsBlock.kt"),
# )
```

Same scenario without a caller (`caller_file=None`): falls through to
step 3 and picks `feature/account/SettingsBlock.kt` (lex-first).

---

## Honouring Kotlin `import` statements (decided: NO for 0.2.0)

A more accurate strategy would scan the caller file's import block:

```kotlin
import es.card.plazo.ui.profile.SettingsBlock
```

…then prefer the exact path match. This works in Kotlin but **not**
symmetrically in SwiftUI (Swift uses module-level imports, not type
imports). To keep cross-platform parity:

- 0.2.0 ships proximity-only (step 1 → 2 → 3 above).
- 0.3.0 may add Kotlin-only `import` resolution if real-world
  ambiguity rates demand it. The dogfood ambiguity-rate metric will
  drive the decision.

---

## Failure modes

| | Failure | Behaviour |
|---|---|---|
| F1 | `name` not in `index.{compose,swiftui}` | Return `None`. Phase 3 emits `ast-unresolved`. |
| F2 | Exactly one candidate | Return it; `ambiguous_alternatives = ()`. |
| F3 | Multiple candidates, none match caller dir / any ancestor | Lex-first wins; rest go to `ambiguous_alternatives`. |
| F4 | `caller_file` is `None` | Skip steps 1–2; go straight to lex-sort. |
| F5 | `caller_file` lives outside `index.root` | Same as F4 — proximity unusable. |

---

## Test strategy

Fixtures under `tests/fixtures/multi_file/resolution/`:

```
resolution_unique/                  → exactly one candidate
resolution_same_dir/                → 3 candidates, one in caller dir
resolution_ancestor_dir/            → 3 candidates, one in caller's parent
resolution_no_caller/               → caller_file=None, lex-first wins
resolution_outside_root/            → caller_file outside index.root
resolution_missing/                 → name not in index → None
```

Assert on:
- `ResolvedPath.path` equals the expected file
- `ambiguous_alternatives` carries every other candidate, sorted
- `None` returned when index has no entry

---

## Public API

```python
# lumo/render/project_index.py (same module as Phase 1)

@dataclass(frozen=True)
class ResolvedPath:
    path: Path
    ambiguous_alternatives: tuple[Path, ...]

def resolve_name(
    index: ProjectIndex,
    name: str,
    *,
    caller_file: Path | None,
    platform: Literal["compose", "swiftui"],
) -> ResolvedPath | None: ...
```

Still no CLI surface. Phase 3 is what ties everything to user-facing
output.

---

## Done-when checklist

- [ ] `ResolvedPath` + `resolve_name` exist
- [ ] All 6 fixture cases pass
- [ ] Lex-sort tested with paths that differ only in case / unicode
- [ ] Performance: 5000-candidate name resolves in <5 ms (it should —
      this is just a dict lookup + path walk)
- [ ] mypy strict clean
