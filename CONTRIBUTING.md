# Contributing to Lumo

Thanks for considering a contribution. Lumo is a small project with strong
opinions about what it is and isn't — please read this before opening a PR.

## What Lumo is

A toolkit for **mobile UI/UX** on Jetpack Compose, Android XML, SwiftUI,
and UIKit. The hard checks (WCAG luminance, OKLCH correction, geometric
parity, Fitts / Hick / Gestalt) run as **deterministic Python tools**.
The Claude Code skill and the MCP server are thin layers over those tools.

## What Lumo is NOT (please don't propose these)

- A code generator (no "Lumo, build me a login screen").
- A design tool with a canvas.
- A replacement for Figma, Mobbin, or Specify.
- Backend-coupled — every check must run locally on the user's machine.
- Multi-platform-everything — Flutter and React Native land in v0.2+.
  Don't open a PR that adds them to v0.1.

A more complete list lives in `ROADMAP.md` under "Non-goals".

## Ground rules

- **No fake numbers.** If a check depends on device-specific constants
  with wide variance across studies, report a relative comparison or
  flag, not a made-up absolute. The honesty rule lives in
  `tools/lumo/theory/__init__.py` — read it before adding new checks.
- **Confidence labels propagate.** Every finding carries `measured`,
  `code-estimated`, or `description-estimated`. If you add a tool that
  takes layout input, propagate this honestly.
- **Tests are non-negotiable.** Every new check needs at least two
  tests: one for the positive case (it fires), one for the negative
  case (it doesn't fire when it shouldn't).
- **No backend.** Local-only is a hard rule in v1. Phase 4 of the roadmap
  considers an optional cloud companion, but anything network in v1 is
  out of scope.

## How to set up

```bash
git clone https://github.com/OneXeor-Dev/lumo.git
cd lumo/tools
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest               # 67 passing
```

For the installer side:

```bash
cd lumo/installer
npm install
node src/index.js --help
```

## How to add a new tool

The skill, MCP server, and SKILL.md all reference tools through one
canonical path. Adding a tool means touching three places:

1. `tools/lumo/<area>/core.py` — pure Python, no IO, no LLM. Returns
   dataclasses with structured findings.
2. `tools/lumo/<area>/cli.py` — argparse wrapper, JSON output mode,
   exit-code legend.
3. `tools/lumo/mcp/server.py` — one `@server.tool()` function that
   forwards to the core API. Add a long docstring (≥80 chars) describing
   *when* the LLM should call it.
4. `skill/SKILL.md` — append to the Tools section and the Decision Tree
   following the Prompt Engineering Principles in `ROADMAP.md`.
5. `tools/tests/test_<area>.py` — tests against the core API plus a
   parity test between MCP wrapper and the direct call.

Then register the entry-point in `tools/pyproject.toml` under
`[project.scripts]` and update the `listInstalledBinaries` array in
`installer/src/lib/python.js` so `lumo doctor` knows the new binary.

## How to file a bug

Open an issue with:

- the input (layout JSON, color pair, etc.)
- the command you ran
- the output you got
- the output you expected
- which platform you're targeting (Compose / XML / SwiftUI / UIKit)

Bugs in the WCAG math should include the W3C-formula expected value so
we can anchor the fix against the spec rather than vibes.

## How to suggest a check

Open an issue first — don't write code yet. The format we'll discuss in:

1. What is the rule (one sentence)
2. What's the underlying source (HIG link, Material link, paper, etc.)
3. What input does it need (layout JSON? color pair? something new?)
4. Is the rule numeric or qualitative? If qualitative, why is it in a
   tool and not in inline SKILL.md guidance?
5. One example of a layout / pair that should trigger it, and one that
   should not.

If we agree it fits, you implement and submit a PR with tests.

## Code style

- Python: ruff defaults, mypy strict
- JavaScript: ESM modules, no TypeScript build step
- Commit messages: conventional commits (`feat:`, `fix:`, `docs:`,
  `chore:`, with `!` suffix for breaking changes)

## License

By contributing you agree your contribution is licensed under MIT,
same as the rest of the project.
