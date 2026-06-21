/**
 * Python detection and lumo-mobile install helpers.
 *
 * Strategy:
 *   - Locate a Python ≥3.10 interpreter (python3, python, py -3 on Windows).
 *   - Maintain a Lumo-owned venv at ~/.lumo/venv so user system Python stays clean.
 *   - Install lumo-mobile into that venv via pip — from PyPI by default,
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
export const LUMO_BINARIES = [
  "lumo-wcag",
  "lumo-theory",
  "lumo-parity",
  "lumo-source",
  "lumo-audit",
  "lumo-figma",
  "lumo-render",
  "lumo-mcp",
];

export function venvBinary(name) {
  const ext = process.platform === "win32" ? ".exe" : "";
  return path.join(VENV_DIR, BIN_DIR, `${name}${ext}`);
}

function parsePythonVersion(output) {
  const match = output.match(/Python (\d+)\.(\d+)/);
  if (!match) return null;
  return { major: Number(match[1]), minor: Number(match[2]) };
}

function isSupportedPythonVersion(version) {
  return Boolean(version && (version.major > 3 || (version.major === 3 && version.minor >= 10)));
}

/** Returns the first usable Python interpreter or throws with install hint. */
export function findPython() {
  const candidates =
    process.platform === "win32"
      ? [["py", "-3"], ["python3"], ["python"]]
      : [["python3"], ["/opt/homebrew/bin/python3"], ["/usr/local/bin/python3"], ["python"]];

  for (const [cmd, ...args] of candidates) {
    const result = spawnSync(cmd, [...args, "--version"], { encoding: "utf8" });
    if (result.status !== 0) continue;
    const out = (result.stdout || result.stderr || "").trim();
    const version = parsePythonVersion(out);
    if (!isSupportedPythonVersion(version)) continue;
    return { cmd, args, version: `${version.major}.${version.minor}` };
  }

  throw new Error(
    "Python 3.10+ not found.\n" +
      "  macOS:     brew install python@3.12\n" +
      "  Ubuntu:    sudo apt install python3.12 python3.12-venv\n" +
      "  Windows:   winget install Python.Python.3.12"
  );
}

function existingVenvIsUsable() {
  const python = venvBinary("python");
  if (!fs.existsSync(VENV_DIR) || !fs.existsSync(python)) return false;
  const result = spawnSync(python, ["--version"], { encoding: "utf8" });
  if (result.status !== 0) return false;
  const out = (result.stdout || result.stderr || "").trim();
  return isSupportedPythonVersion(parsePythonVersion(out));
}

/** Create ~/.lumo/venv if it doesn't already exist. */
export async function ensureVenv() {
  fs.mkdirSync(LUMO_HOME, { recursive: true });
  if (existingVenvIsUsable()) {
    return; // already there
  }
  if (fs.existsSync(VENV_DIR)) {
    fs.rmSync(VENV_DIR, { recursive: true, force: true });
  }
  const py = findPython();
  await execFileP(py.cmd, [...py.args, "-m", "venv", VENV_DIR]);
}

/**
 * Install lumo-mobile into the Lumo-owned venv.
 *
 * @param {object} opts
 * @param {string} [opts.source]  Local path to install from (used with --dev).
 *                                When omitted, installs `lumo-mobile` from PyPI.
 */
export async function installLumoTools(opts = {}) {
  await ensureVenv();
  const python = venvBinary("python");
  await execFileP(
    python,
    ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
    { maxBuffer: 20 * 1024 * 1024 }
  );
  const args = ["install", "--upgrade"];
  if (opts.source) {
    args.push("-e", opts.source);
  } else {
    args.push("lumo-mobile");
  }
  await execFileP(python, ["-m", "pip", ...args], { maxBuffer: 20 * 1024 * 1024 });
}

/** Sanity check: each registered CLI binary actually exists in the venv. */
export function listInstalledBinaries() {
  return LUMO_BINARIES.map((name) => ({
    name,
    path: venvBinary(name),
    exists: fs.existsSync(venvBinary(name)),
  }));
}
