import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import kleur from "kleur";
import prompts from "prompts";

import { CLIENTS, getClient } from "../lib/clients.js";
import { installLumoTools, listInstalledBinaries } from "../lib/python.js";
import { findSkillSource, installSkill } from "../lib/skill.js";
import { registerMcp } from "../lib/mcp.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** Resolve --dev source: the repo root above installer/. */
function devSource() {
  return path.resolve(__dirname, "..", "..", "..", "tools");
}

async function pickClient(supplied, allFlag) {
  if (allFlag) return CLIENTS.filter((c) => c.id !== "generic");
  if (supplied) return [getClient(supplied)];

  const { ai } = await prompts({
    type: "select",
    name: "ai",
    message: "Which AI client are you installing Lumo for?",
    choices: CLIENTS.map((c) => ({ title: c.label, value: c.id })),
    initial: 0,
  });
  if (!ai) {
    throw new Error("No client selected.");
  }
  return [getClient(ai)];
}

export async function initCommand(opts) {
  console.log(kleur.bold().cyan("\n• Lumo installer\n"));

  const targets = await pickClient(opts.ai, opts.all);

  console.log(kleur.dim("→ installing Python tools (lumo-mobile) into ~/.lumo/venv ..."));
  try {
    if (opts.dev) {
      const dev = devSource();
      console.log(kleur.dim(`  using --dev source ${dev}`));
      await installLumoTools({ source: dev });
    } else {
      await installLumoTools();
    }
  } catch (err) {
    throw new Error(`pip install failed: ${err.stderr || err.message || err}`);
  }

  const bins = listInstalledBinaries();
  const missing = bins.filter((b) => !b.exists);
  if (missing.length > 0) {
    throw new Error(
      "Some Lumo CLIs did not install:\n  " +
        missing.map((b) => `${b.name} (expected at ${b.path})`).join("\n  ")
    );
  }
  console.log(kleur.green(`✓ Python tools installed`));
  bins.forEach((b) => console.log(kleur.dim(`  ${b.name}  ${b.path}`)));

  const skillSource = findSkillSource();

  for (const client of targets) {
    console.log(kleur.bold(`\n→ ${client.label}`));
    if (!client.skillDir) {
      console.log(kleur.dim("  generic mode — nothing to copy automatically."));
      console.log(kleur.dim("  Skill bundle is at: ") + skillSource);
      console.log(kleur.dim("  MCP server command: ") + listInstalledBinaries()[3].path);
      continue;
    }

    installSkill(client.skillDir);
    console.log(kleur.green(`  ✓ skill copied to ${client.skillDir}`));

    if (opts.mcp !== false && client.mcpConfigPath && client.mcpConfigKey) {
      try {
        const { configPath, command } = registerMcp(client.mcpConfigPath, client.mcpConfigKey);
        console.log(kleur.green(`  ✓ MCP registered in ${configPath}`));
        console.log(kleur.dim(`    command: ${command}`));
      } catch (err) {
        console.log(
          kleur.yellow(`  ! MCP registration skipped: ${err.message}`)
        );
      }
    } else if (opts.mcp === false) {
      console.log(kleur.dim("  MCP registration skipped (--no-mcp)."));
    }
  }

  console.log(kleur.bold().green("\n✓ Lumo installation complete.\n"));
  console.log(kleur.dim("Next: open your AI client and ask it to use the Lumo skill."));
  console.log(kleur.dim("Verify any time with: lumo doctor\n"));
}
