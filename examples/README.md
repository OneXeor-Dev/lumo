# examples/

Small, hand-built layouts the Lumo tools and tests use as anchors. Every
file is referenced from at least one of:

- the worked examples in `skill/SKILL.md`
- the smoke commands in `README.md`
- the CI job that pip-installs `lumo-mobile` and runs each CLI

Keep them small, keep them honest. If you change one, make sure the
findings the README screenshot promises still match.

## What each file is for

| File | Used by | What it demonstrates |
|---|---|---|
| `theory_bad_layout.json` | `lumo-theory check` | Several issues at once — undersized icon (`close` is 32 dp, below 48 dp Material minimum), primary action `save` in a top corner (`reach_primary_in_top_corner`), 7 equal-weight nav items (Hick overload). Used as the "find everything wrong" demo. |
| `theory_good_layout.json` | `lumo-theory check` | A well-designed Material screen — bottom nav with 4 items, well-separated content groups, primary CTA in the safe bottom area. Tool returns "OK no findings". Used to show the tool doesn't false-positive on healthy UI. |
| `parity_android.json` | `lumo-parity diff` | The Android side: 5 elements including `card_offer` at `height=16` and a `fab_add` that has no iOS twin. |
| `parity_ios.json` | `lumo-parity diff` | The iOS side: paired with `parity_android.json`. `card_offer` is at `height=48` (the classic "iOS uses 3× because Retina" junior bug), `nav_back` is at 44 pt (legitimate platform default — Lumo whitelists it), `fab_add` is missing entirely. |
| `lumo.config.json` | `lumo-parity diff --config` | Tiny design system: `primary_button_height: 56`. Both Android and iOS layouts comply, so this config doesn't add findings — it's here as the "happy path" example. Edit it to `48` and re-run parity to see two new `design_system_height_mismatch_*` findings appear. |

## Layout JSON schema (quick reference)

```json
{
  "screen":  { "width": 411, "height": 891, "unit": "dp" },
  "source":  "measured | code-estimated | description-estimated",
  "elements": [
    {
      "id": "btn_continue",
      "role": "primary_action",
      "x": 24, "y": 800, "w": 363, "h": 56,
      "group": "form_actions",
      "weight": "primary"
    }
  ]
}
```

The `source` field is honesty about how the coordinates were obtained:

- `measured` — from a real device or a snapshot-testing framework
  (Espresso, XCUITest, Compose `onGloballyPositioned`, SwiftUI
  `GeometryReader`, Paparazzi, `xcodebuild test --only-testing`).
- `code-estimated` — parsed statically from Compose / SwiftUI source.
  Theme tokens, `fillMaxWidth`, dynamic type are guesses at this layer.
- `description-estimated` — built from a screenshot description or a
  natural-language prompt. Lowest confidence.

The Lumo tools propagate this label to every finding so the consumer
can weigh trust honestly.

See `skill/SKILL.md` for the full schema (roles, weights, group semantics)
and `tools/lumo/theory/core.py` / `tools/lumo/parity/core.py` for the
authoritative type definitions.
