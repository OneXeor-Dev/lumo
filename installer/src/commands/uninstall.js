import kleur from "kleur";
import prompts from "prompts";

import { CLIENTS, getClient } from "../lib/clients.js";
import { unregisterMcp } from "../lib/mcp.js";
import { removeSkill } from "../lib/skill.js";

async function pickClient(supplied, allFlag) {
  if (allFlag) return CLIENTS.filter((c) => c.id !== "generic");
  if (supplied) return [getClient(supplied)];

  const { ai } = await prompts({
    type: "select",
    name: "ai",
    message: "Remove Lumo from which client?",
    choices: CLIENTS.filter((c) => c.skillDir).map((c) => ({ title: c.label, value: c.id })),
    initial: 0,
  });
  if (!ai) throw new Error("No client selected.");
  return [getClient(ai)];
}

export async function uninstallCommand(opts) {
  console.log(kleur.bold().cyan("\n• Lumo uninstaller\n"));

  const targets = await pickClient(opts.ai, opts.all);

  for (const client of targets) {
    if (!client.skillDir) continue;
    console.log(kleur.bold(`\n→ ${client.label}`));

    const removed = removeSkill(client.skillDir);
    if (removed) {
      console.log(kleur.green(`  ✓ skill removed from ${client.skillDir}`));
    } else {
      console.log(kleur.dim(`  skill not present (${client.skillDir})`));
    }

    if (client.mcpConfigPath && client.mcpConfigKey) {
      const unreg = unregisterMcp(client.mcpConfigPath, client.mcpConfigKey);
      if (unreg) {
        console.log(kleur.green(`  ✓ MCP entry removed from ${client.mcpConfigPath}`));
      } else {
        console.log(kleur.dim(`  no MCP entry to remove`));
      }
    }
  }

  console.log(kleur.dim("\nPython tools (~/.lumo/venv) left intact."));
  console.log(kleur.dim("Remove them manually with: rm -rf ~/.lumo\n"));
}
