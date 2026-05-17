import fs from "node:fs";

import { CLIENTS } from "../lib/clients.js";
import { LUMO_HOME, listInstalledBinaries, venvBinary } from "../lib/python.js";
import { bold, cyan, dim, green, red, yellow } from "../lib/style.js";

function row(ok, label, detail = "") {
  const icon = ok ? green("✓") : red("✗");
  const text = ok ? label : yellow(label);
  const trail = detail ? "  " + dim(detail) : "";
  process.stdout.write(`  ${icon} ${text}${trail}\n`);
}

export async function doctorCommand() {
  process.stdout.write("\n" + bold(cyan("• lumo doctor")) + "\n\n");

  process.stdout.write(bold("Python tools") + "\n");
  row(fs.existsSync(LUMO_HOME), "Lumo home", LUMO_HOME);
  row(fs.existsSync(venvBinary("python")), "venv Python", venvBinary("python"));
  for (const bin of listInstalledBinaries()) {
    row(bin.exists, bin.name, bin.path);
  }

  process.stdout.write("\n" + bold("Client integrations") + "\n");
  for (const client of CLIENTS) {
    if (!client.skillDir) continue;
    const skillPresent = fs.existsSync(client.skillDir);
    row(skillPresent, `${client.label} skill`, client.skillDir);

    if (client.mcpConfigPath) {
      if (!fs.existsSync(client.mcpConfigPath)) {
        row(false, `${client.label} MCP config`, `not found at ${client.mcpConfigPath}`);
        continue;
      }
      try {
        const raw = fs.readFileSync(client.mcpConfigPath, "utf8");
        const data = JSON.parse(raw);
        const hasLumo = Boolean(data[client.mcpConfigKey]?.lumo);
        row(hasLumo, `${client.label} MCP registered`, client.mcpConfigPath);
      } catch (err) {
        row(false, `${client.label} MCP config unparseable`, err.message);
      }
    }
  }

  process.stdout.write("\n" + dim("Run `lumo init` to install or repair any missing pieces.") + "\n\n");
}
