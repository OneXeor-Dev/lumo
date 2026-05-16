/**
 * Supported AI client registry.
 *
 * Each entry tells the installer:
 *   - where to copy the SKILL.md (skillDir, optional)
 *   - where to register the MCP server (mcpConfigPath + mcpConfigKey, optional)
 *   - how to detect whether the client is installed (detectPaths)
 *
 * Adding a new client = adding one entry here. The init / uninstall / doctor
 * commands all read from this registry.
 */

import os from "node:os";
import path from "node:path";

const HOME = os.homedir();

/** @typedef {{
 *   id: string,
 *   label: string,
 *   skillDir?: string,
 *   mcpConfigPath?: string,
 *   mcpConfigKey?: string,
 *   detectPaths: string[],
 * }} ClientSpec
 */

/** @type {ClientSpec[]} */
export const CLIENTS = [
  {
    id: "claude",
    label: "Claude Code",
    // Claude Code reads skills from ~/.claude/skills/<name>/SKILL.md
    skillDir: path.join(HOME, ".claude", "skills", "lumo"),
    // Claude Desktop / Claude Code share a config file for MCP servers.
    // On macOS the canonical path is ~/Library/Application Support/Claude/claude_desktop_config.json
    // We fall back to ~/.claude/claude_desktop_config.json if the Library path doesn't exist.
    mcpConfigPath:
      process.platform === "darwin"
        ? path.join(HOME, "Library", "Application Support", "Claude", "claude_desktop_config.json")
        : path.join(HOME, ".claude", "claude_desktop_config.json"),
    mcpConfigKey: "mcpServers",
    detectPaths: [path.join(HOME, ".claude"), path.join(HOME, "Library", "Application Support", "Claude")],
  },
  {
    id: "cursor",
    label: "Cursor",
    // Cursor reads project rules from .cursorrules and global rules from
    // ~/.cursor/rules/. For now Lumo writes a small pointer rule that
    // delegates the heavy lifting to the MCP server.
    skillDir: path.join(HOME, ".cursor", "rules", "lumo"),
    mcpConfigPath: path.join(HOME, ".cursor", "mcp.json"),
    mcpConfigKey: "mcpServers",
    detectPaths: [path.join(HOME, ".cursor")],
  },
  {
    id: "codex",
    label: "OpenAI Codex CLI",
    // Codex CLI looks for skills in ~/.codex/skills/ when present.
    skillDir: path.join(HOME, ".codex", "skills", "lumo"),
    mcpConfigPath: path.join(HOME, ".codex", "mcp.json"),
    mcpConfigKey: "mcpServers",
    detectPaths: [path.join(HOME, ".codex")],
  },
  {
    id: "generic",
    label: "Generic / manual (just print install paths)",
    // No skillDir or mcpConfigPath — generic mode only prints guidance.
    detectPaths: [],
  },
];

export function getClient(id) {
  const client = CLIENTS.find((c) => c.id === id);
  if (!client) {
    throw new Error(
      `Unknown client: ${id}. Supported: ${CLIENTS.map((c) => c.id).join(", ")}`
    );
  }
  return client;
}
