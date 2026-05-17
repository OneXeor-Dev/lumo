import { CLIENTS, getClient } from "../lib/clients.js";
import { unregisterMcp } from "../lib/mcp.js";
import { removeSkill } from "../lib/skill.js";
import { select } from "../lib/prompt.js";
import { bold, cyan, dim, green } from "../lib/style.js";

async function pickClients(supplied, allFlag) {
  if (allFlag) return CLIENTS.filter((c) => c.id !== "generic");
  if (supplied) return [getClient(supplied)];

  const ai = await select({
    message: "Remove Lumo from which client?",
    choices: CLIENTS.filter((c) => c.skillDir).map((c) => ({ title: c.label, value: c.id })),
    initial: 0,
  });
  if (!ai) throw new Error("No client selected.");
  return [getClient(ai)];
}

export async function uninstallCommand(opts) {
  process.stdout.write("\n" + bold(cyan("• Lumo uninstaller")) + "\n\n");

  const targets = await pickClients(opts.ai, opts.all);

  for (const client of targets) {
    if (!client.skillDir) continue;
    process.stdout.write("\n" + bold(`→ ${client.label}`) + "\n");

    const removed = removeSkill(client.skillDir);
    if (removed) {
      process.stdout.write(green(`  ✓ skill removed from ${client.skillDir}\n`));
    } else {
      process.stdout.write(dim(`  skill not present (${client.skillDir})\n`));
    }

    if (client.mcpConfigPath && client.mcpConfigKey) {
      const unreg = unregisterMcp(client.mcpConfigPath, client.mcpConfigKey);
      if (unreg) {
        process.stdout.write(green(`  ✓ MCP entry removed from ${client.mcpConfigPath}\n`));
      } else {
        process.stdout.write(dim(`  no MCP entry to remove\n`));
      }
    }
  }

  process.stdout.write("\n" + dim("Python tools (~/.lumo/venv) left intact.") + "\n");
  process.stdout.write(dim("Remove them manually with: rm -rf ~/.lumo") + "\n\n");
}
