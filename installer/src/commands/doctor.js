import fs from "node:fs";

import kleur from "kleur";

import { CLIENTS } from "../lib/clients.js";
import { LUMO_HOME, listInstalledBinaries, venvBinary } from "../lib/python.js";

function row(ok, label, detail = "") {
  const icon = ok ? kleur.green("✓") : kleur.red("✗");
  const text = ok ? kleur.white(label) : kleur.yellow(label);
  console.log(`  ${icon} ${text}${detail ? kleur.dim("  " + detail) : ""}`);
}

export async function doctorCommand() {
  console.log(kleur.bold().cyan("\n• lumo doctor\n"));

  console.log(kleur.bold("Python tools"));
  row(fs.existsSync(LUMO_HOME), `Lumo home`, LUMO_HOME);
  row(fs.existsSync(venvBinary("python")), `venv Python`, venvBinary("python"));
  for (const bin of listInstalledBinaries()) {
    row(bin.exists, bin.name, bin.path);
  }

  console.log("");
  console.log(kleur.bold("Client integrations"));
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

  console.log("");
  console.log(kleur.dim("Run `lumo init` to install or repair any missing pieces."));
  console.log("");
}
