# 03 — Outputs

[← back to index](./README.md)

Finding shape, severity derivation, exit codes.

---

## Finding envelope

Same shape as `lumo-theory` / `lumo-source`, with two spec-specific
fields: `confidence` and `evidence`.

```json
{
  "tool": "lumo-spec",
  "source": "llm-derived",
  "model": "claude-haiku-4-5-20251001",
  "spec": {
    "source_type": "jira",
    "source_id": "CRDES-1234",
    "fetched_at": "2026-05-26T14:12:33Z",
    "character_count": 4821
  },
  "layout": {
    "source": "measured",
    "elements_count": 27
  },
  "findings": [
    {
      "id": "missing_required_element",
      "severity": "high",
      "confidence": "high",
      "element": null,
      "message": "Spec requires a 'Back' button in the header; not present in layout.",
      "evidence": "User can return to the previous step at any time via a back arrow in the top-left.",
      "recommendation": "Add a back button to the header. Material: IconButton with Icons.ArrowBack; SwiftUI: toolbar leading item with Image(systemName: \"chevron.left\")."
    },
    {
      "id": "element_count_mismatch",
      "severity": "medium",
      "confidence": "high",
      "element": null,
      "message": "Spec calls for 3 input fields (name, email, phone); layout has 5.",
      "evidence": "The form contains exactly three fields: full name, email, and phone number.",
      "recommendation": "Remove the two extra input fields, or confirm with the PM that the spec is outdated."
    },
    {
      "id": "behavioural_constraint_violation",
      "severity": "medium",
      "confidence": "medium",
      "element": "btn_continue",
      "message": "Spec says CTA hidden until form is valid; layout shows it always.",
      "evidence": "The Continue button only becomes visible once all required fields are filled and validated.",
      "recommendation": "Designer should add a hidden / disabled state for btn_continue."
    }
  ],
  "summary": {
    "total": 3,
    "by_severity": { "high": 1, "medium": 2, "low": 0 },
    "by_confidence": { "high": 2, "medium": 1, "low": 0 }
  }
}
```

---

## Finding `id` enum (v1)

| id | When to use |
|---|---|
| `missing_required_element` | Spec names a UI element / state / control that's absent from the layout |
| `element_count_mismatch` | Spec quantifies (e.g. "3 fields") and layout doesn't match |
| `behavioural_constraint_violation` | Spec describes state / visibility / order, layout violates |
| `copy_mismatch` | Spec quotes specific text, layout shows different text |
| `extraneous_element` | Layout includes elements the spec doesn't mention (low confidence by default — spec may be incomplete) |
| `ambiguous_requirement` | Spec is genuinely unclear; flagged for human resolution, not a defect |

Adding a new id requires updating the schema + golden cases. Don't
let the LLM invent ids — the structured-output schema enforces the enum.

---

## Severity derivation

Most product specs do **not** use RFC 2119 wording — they say "нужно",
"add a", "the screen has", not "must / should / may". So the primary
path is LLM inference from context, with the recommendation explaining
why a severity was chosen. Inferred-severity findings always carry
`confidence: medium` or `low`, never `high`.

When RFC 2119 keywords *are* present, they map directly (a useful
signal, not the common case):

| Spec keyword | Severity |
|---|---|
| `must`, `required`, `shall` | high |
| `should`, `recommended` | medium |
| `may`, `optional`, `nice to have` | low |

---

## Exit codes

- `0` — no findings.
- `1` — findings reported.
- `2` — tool error (unreachable source, auth failure, malformed
  layout, spec too long, LLM error, schema-validation failure).

`1` vs `2` is the standard Lumo convention — `1` means "the tool
worked and found problems", `2` means "the tool itself failed".
CI scripts use this to distinguish "needs designer attention" from
"needs ops attention".

---

## Text output (default, no `--json`)

```
SPEC vs LAYOUT — CRDES-1234 vs screen.json
Model: claude-haiku-4-5-20251001  ·  Spec chars: 4,821  ·  Layout elements: 27

FOUND  3 findings (1 high, 2 medium, 0 low)

  1. [HIGH    ] missing_required_element
     Spec requires a 'Back' button in the header; not present in layout.
     Evidence: "User can return to the previous step at any time via a back arrow in the top-left."
     → Add a back button to the header.
     Confidence: high

  2. [MEDIUM  ] element_count_mismatch
     ...
```

Same format as `lumo-theory` so consumers (humans, CI logs, annotated
PNG generator) treat output uniformly.
