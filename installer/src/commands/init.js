import path from "node:path";
import { fileURLToPath } from "node:url";

import { CLIENTS, getClient } from "../lib/clients.js";
import { installLumoTools, listInstalledBinaries } from "../lib/python.js";
import { findSkillSource, installSkill } from "../lib/skill.js";
import { registerMcp } from "../lib/mcp.js";
import { select } from "../lib/prompt.js";
import { bold, cyan, dim, green, yellow } from "../lib/style.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** Resolve --dev source: the repo root above installer/. */
function devSource() {
  return path.resolve(__dirname, "..", "..", "..", "tools");
}

async function pickClients(supplied, allFlag) {
  if (allFlag) return CLIENTS.filter((c) => c.id !== "generic");
  if (supplied) return [getClient(supplied)];

  const ai = await select({
    message: "Which AI client are you installing Lumo for?",
    choices: CLIENTS.map((c) => ({ title: c.label, value: c.id })),
    initial: 0,
  });
  if (!ai) throw new Error("No client selected.");
  return [getClient(ai)];
}

export async function initCommand(opts) {
  process.stdout.write("\n" + bold(cyan("• Lumo installer")) + "\n\n");

  const targets = await pickClients(opts.ai, opts.all);

  process.stdout.write(dim("→ installing Python tools (lumo-mobile) into ~/.lumo/venv ...\n"));
  try {
    if (opts.dev) {
      const dev = devSource();
      process.stdout.write(dim(`  using --dev source ${dev}\n`));
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
  process.stdout.write(green("✓ Python tools installed\n"));
  bins.forEach((b) => process.stdout.write(dim(`  ${b.name}  ${b.path}\n`)));

  const skillSource = findSkillSource();

  for (const client of targets) {
    process.stdout.write("\n" + bold(`→ ${client.label}`) + "\n");
    if (!client.skillDir) {
      process.stdout.write(dim("  generic mode — nothing to copy automatically.\n"));
      process.stdout.write(dim("  Skill bundle is at: ") + skillSource + "\n");
      process.stdout.write(dim("  MCP server command: ") + listInstalledBinaries()[3].path + "\n");
      continue;
    }

    installSkill(client.skillDir);
    process.stdout.write(green(`  ✓ skill copied to ${client.skillDir}\n`));

    if (opts.mcp !== false && client.mcpConfigPath && client.mcpConfigKey) {
      try {
        const { configPath, command } = registerMcp(client.mcpConfigPath, client.mcpConfigKey);
        process.stdout.write(green(`  ✓ MCP registered in ${configPath}\n`));
        process.stdout.write(dim(`    command: ${command}\n`));
      } catch (err) {
        process.stdout.write(yellow(`  ! MCP registration skipped: ${err.message}\n`));
      }
    } else if (opts.mcp === false) {
      process.stdout.write(dim("  MCP registration skipped (--no-mcp).\n"));
    }
  }

  process.stdout.write("\n" + bold(green("✓ Lumo installation complete.")) + "\n\n");
  process.stdout.write(dim("Next: open your AI client and ask it to use the Lumo skill.\n"));
  process.stdout.write(dim("Verify any time with: lumo doctor\n\n"));
}
