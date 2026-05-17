# lumo — installer

One-command installer for [Lumo](https://github.com/OneXeor-Dev/lumo): mobile
UI/UX design intelligence for AI coding assistants.

```bash
npx @onexeor/lumo init                    # interactive — picks your AI client
npx @onexeor/lumo init --ai claude        # explicit target
npx @onexeor/lumo init --all              # install everywhere supported
npx @onexeor/lumo init --ai claude --dev  # install from a local git clone (contributors)
npx @onexeor/lumo init --no-mcp           # skill only, skip MCP server registration

# After install the binary is `lumo` (the scoped package name is only
# needed to disambiguate during install):
lumo doctor                               # verify every Lumo piece is in place
lumo uninstall --ai claude                # remove the skill (Python tools stay)
```

Supported AI clients in v0.1:

- **Claude Code** — copies the skill into `~/.claude/skills/lumo/` and
  registers the MCP server in `claude_desktop_config.json`
- **Cursor** — installs to `~/.cursor/rules/lumo/` and registers MCP in
  `~/.cursor/mcp.json`
- **OpenAI Codex CLI** — installs to `~/.codex/skills/lumo/` and
  registers MCP in `~/.codex/mcp.json`
- **generic** — prints install paths so you can wire it into anything
  not listed above

Under the hood the installer:

1. Locates a Python 3.10+ interpreter and creates a Lumo-owned venv at
   `~/.lumo/venv` so your system Python stays clean.
2. `pip install`s [`lumo-mobile`](https://pypi.org/project/lumo-mobile/) into
   that venv. The CLIs (`lumo-wcag`, `lumo-theory`, `lumo-parity`,
   `lumo-mcp`) become available at absolute paths the MCP configs point to.
3. Copies the `SKILL.md` bundle into the chosen client's skill directory.
4. Merges a `{ "mcpServers": { "lumo": { "command": "..." } } }` block
   into the client's MCP config — non-destructive, backs up the file once
   before the first write.

The installer never modifies anything outside `~/.lumo`, the chosen
client's skill directory, and the chosen client's MCP config file.

## Publishing (maintainers only)

The installer ships with no npm lifecycle scripts on purpose — Socket.dev
and similar supply-chain scanners penalise packages that auto-execute
code on install or pack, even when that code is benign. To publish a
new version:

```bash
cd installer
bash scripts/release.sh --dry-run   # bundles /skill into installer/skill, npm pack --dry-run
bash scripts/release.sh             # same, but actually publishes
```

`release.sh` is the only sanctioned way to build the tarball. Running
`npm pack` or `npm publish` directly will produce a broken tarball
without the bundled `SKILL.md`, so `lumo init` would fail
post-install. The script makes the bundling explicit and Socket-clean.

## License

MIT
