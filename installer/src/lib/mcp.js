/**
 * MCP server registration in a client's JSON config.
 *
 * All supported MCP clients (Claude, Cursor, Codex, etc) use roughly the
 * same shape:
 *
 *   {
 *     "mcpServers": {
 *       "lumo": { "command": "/abs/path/to/lumo-mcp", "args": [] }
 *     }
 *   }
 *
 * We:
 *   - create the file if missing
 *   - merge into an existing object without clobbering other servers
 *   - keep a backup copy as <file>.lumo.bak the first time we write
 */

import fs from "node:fs";
import path from "node:path";

import { venvBinary } from "./python.js";

const SERVER_KEY = "lumo";

function loadJsonOrEmpty(filePath) {
  if (!fs.existsSync(filePath)) return {};
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (err) {
    throw new Error(
      `${filePath} exists but is not valid JSON. Fix it manually before re-running lumo init.\n  parse error: ${err.message}`
    );
  }
}

function backupOnce(filePath) {
  const backup = `${filePath}.lumo.bak`;
  if (fs.existsSync(filePath) && !fs.existsSync(backup)) {
    fs.copyFileSync(filePath, backup);
  }
}

/** Register lumo-mcp under the client's mcpServers key. */
export function registerMcp(configPath, mcpKey) {
  const lumoMcp = venvBinary("lumo-mcp");

  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  backupOnce(configPath);

  const config = loadJsonOrEmpty(configPath);
  config[mcpKey] = config[mcpKey] || {};
  config[mcpKey][SERVER_KEY] = {
    command: lumoMcp,
    args: [],
  };

  fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n");
  return { configPath, command: lumoMcp };
}

/** Remove the `lumo` entry from the client's mcpServers, if present. */
export function unregisterMcp(configPath, mcpKey) {
  if (!fs.existsSync(configPath)) return false;
  const config = loadJsonOrEmpty(configPath);
  if (!config[mcpKey] || !config[mcpKey][SERVER_KEY]) return false;
  delete config[mcpKey][SERVER_KEY];
  // Drop the mcp key entirely if it's now empty.
  if (Object.keys(config[mcpKey]).length === 0) delete config[mcpKey];
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n");
  return true;
}
