/**
 * Python detection and lumo-tools install helpers.
 *
 * Strategy:
 *   - Locate a Python ≥3.10 interpreter (python3, python, py -3 on Windows).
 *   - Maintain a Lumo-owned venv at ~/.lumo/venv so user system Python stays clean.
 *   - Install lumo-tools into that venv via pip — from PyPI by default,
 *     from a local git path when --dev was passed.
 *   - Expose absolute paths to each console script so SKILL.md and MCP configs
 *     can reference them without depending on PATH.
 */

import { execFile, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileP = promisify(execFile);

export const LUMO_HOME = path.join(os.homedir(), ".lumo");
export const VENV_DIR = path.join(LUMO_HOME, "venv");
const BIN_DIR = process.platform === "win32" ? "Scripts" : "bin";

export function venvBinary(name) {
  const ext = process.platform === "win32" ? ".exe" : "";
  return path.join(VENV_DIR, BIN_DIR, `${name}${ext}`);
}

/** Returns the first usable Python interpreter or throws with install hint. */
export function findPython() {
  const candidates =
    process.platform === "win32"
      ? [["py", "-3"], ["python3"], ["python"]]
      : [["python3"], ["python"]];

  for (const [cmd, ...args] of candidates) {
    const result = spawnSync(cmd, [...args, "--version"], { encoding: "utf8" });
    if (result.status !== 0) continue;
    const out = (result.stdout || result.stderr || "").trim();
    const match = out.match(/Python (\d+)\.(\d+)/);
    if (!match) continue;
    const major = Number(match[1]);
    const minor = Number(match[2]);
    if (major < 3 || (major === 3 && minor < 10)) continue;
    return { cmd, args, version: `${major}.${minor}` };
  }

  throw new Error(
    "Python 3.10+ not found.\n" +
      "  macOS:     brew install python@3.12\n" +
      "  Ubuntu:    sudo apt install python3.12 python3.12-venv\n" +
      "  Windows:   winget install Python.Python.3.12"
  );
}

/** Create ~/.lumo/venv if it doesn't already exist. */
export async function ensureVenv() {
  fs.mkdirSync(LUMO_HOME, { recursive: true });
  if (fs.existsSync(VENV_DIR) && fs.existsSync(venvBinary("python"))) {
    return; // already there
  }
  const py = findPython();
  await execFileP(py.cmd, [...py.args, "-m", "venv", VENV_DIR]);
}

/**
 * Install lumo-tools into the Lumo-owned venv.
 *
 * @param {object} opts
 * @param {string} [opts.source]  Local path to install from (used with --dev).
 *                                When omitted, installs `lumo-tools` from PyPI.
 */
export async function installLumoTools(opts = {}) {
  await ensureVenv();
  const pip = venvBinary("pip");
  const args = ["install", "--upgrade"];
  if (opts.source) {
    args.push("-e", opts.source);
  } else {
    args.push("lumo-tools");
  }
  await execFileP(pip, args, { maxBuffer: 20 * 1024 * 1024 });
}

/** Sanity check: each registered CLI binary actually exists in the venv. */
export function listInstalledBinaries() {
  const names = ["lumo-wcag", "lumo-theory", "lumo-parity", "lumo-mcp"];
  return names.map((name) => ({
    name,
    path: venvBinary(name),
    exists: fs.existsSync(venvBinary(name)),
  }));
}
