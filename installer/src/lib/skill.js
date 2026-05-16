/**
 * Skill file deployment.
 *
 * Copies the SKILL.md (and any references/) from the Lumo repo into the
 * target client's skills directory. We resolve the source skill bundle
 * relative to this installer file so it works in three modes:
 *
 *   1. `npm install -g lumo` — npm copied the installer next to the
 *      bundled skill/ directory.
 *   2. `npx lumo init` — same as above but transient.
 *   3. `node installer/src/index.js init --dev` from a fresh git clone —
 *      the skill/ directory is one level up from installer/.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** Find the repo's skill/ directory regardless of install mode. */
export function findSkillSource() {
  const candidates = [
    path.resolve(__dirname, "..", "..", "..", "skill"), // installer/src/lib → repo/skill
    path.resolve(__dirname, "..", "..", "skill"),       // bundled-with-npm layout
    path.resolve(__dirname, "skill"),                   // any other co-located case
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "SKILL.md"))) return candidate;
  }
  throw new Error(
    "Could not find the Lumo skill/ directory next to the installer. " +
      "If you're running from a custom checkout, pass --dev with the repo root."
  );
}

/** Recursive copy. Overwrites existing files; never deletes the destination root. */
export function copyDirectory(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name);
    const to = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDirectory(from, to);
    } else {
      fs.copyFileSync(from, to);
    }
  }
}

/** Install the skill into a client's skill directory. Returns the dest path. */
export function installSkill(targetDir) {
  const source = findSkillSource();
  copyDirectory(source, targetDir);
  return targetDir;
}

/** Remove a previously-installed skill directory (no-op if not present). */
export function removeSkill(targetDir) {
  if (!fs.existsSync(targetDir)) return false;
  fs.rmSync(targetDir, { recursive: true, force: true });
  return true;
}
