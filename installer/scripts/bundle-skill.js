#!/usr/bin/env node
/**
 * Pre-pack step: copy ../skill into installer/skill so the published
 * tarball ships the SKILL.md bundle alongside the installer code.
 *
 * Why: when a user runs `npx @onexeor/lumo init`, npm extracts ONLY the
 * tarball — there is no git repo on disk. `findSkillSource()` looks for
 * a sibling `skill/` directory; that directory has to be inside the
 * published package.
 *
 * We deliberately keep installer/skill out of git (.gitignored) so the
 * source of truth stays at the repo root.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const SOURCE = path.resolve(__dirname, "..", "..", "skill");
const TARGET = path.resolve(__dirname, "..", "skill");

function copyDirectory(src, dest) {
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

if (!fs.existsSync(path.join(SOURCE, "SKILL.md"))) {
  console.error(`prepack: source skill bundle not found at ${SOURCE}`);
  process.exit(1);
}

fs.rmSync(TARGET, { recursive: true, force: true });
copyDirectory(SOURCE, TARGET);

console.log(`prepack: bundled ${SOURCE} → ${TARGET}`);
