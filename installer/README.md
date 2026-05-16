# lumo — installer

One-command installer for [Lumo](https://github.com/OneXeor/lumo): mobile
UI/UX design intelligence for AI coding assistants.

```bash
npx lumo init                    # interactive — picks your AI client
npx lumo init --ai claude        # explicit target
npx lumo init --all              # install everywhere supported
npx lumo init --ai claude --dev  # install from a local git clone (contributors)
npx lumo init --no-mcp           # skill only, skip MCP server registration

npx lumo doctor                  # verify every Lumo piece is in place
npx lumo uninstall --ai claude   # remove the skill (Python tools stay)
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
2. `pip install`s [`lumo-tools`](https://pypi.org/project/lumo-tools/) into
   that venv. The CLIs (`lumo-wcag`, `lumo-theory`, `lumo-parity`,
   `lumo-mcp`) become available at absolute paths the MCP configs point to.
3. Copies the `SKILL.md` bundle into the chosen client's skill directory.
4. Merges a `{ "mcpServers": { "lumo": { "command": "..." } } }` block
   into the client's MCP config — non-destructive, backs up the file once
   before the first write.

The installer never modifies anything outside `~/.lumo`, the chosen
client's skill directory, and the chosen client's MCP config file.

## License

MIT
