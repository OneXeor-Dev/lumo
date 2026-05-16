#!/usr/bin/env node
/**
 * lumo — mobile UI/UX design intelligence installer.
 *
 * Subcommands:
 *   init [--ai <client>] [--all]   Install the Lumo skill (+ optional MCP) into an AI client.
 *   doctor                         Verify Python tools + skill installation.
 *   uninstall [--ai <client>]      Remove the Lumo skill (Python tools left intact).
 *
 * Supported AI clients in v0.1: claude, cursor, codex, generic.
 * Other clients can still consume Lumo via `npx skills add OneXeor-Dev/lumo`
 * or by pointing their MCP config at `lumo-mcp`.
 */

import { Command } from "commander";
import kleur from "kleur";

import { initCommand } from "./commands/init.js";
import { doctorCommand } from "./commands/doctor.js";
import { uninstallCommand } from "./commands/uninstall.js";

const program = new Command();

program
  .name("lumo")
  .description(
    "Mobile UI/UX design intelligence — WCAG / parity / cognitive-science checks " +
      "for Jetpack Compose, Android XML, SwiftUI, UIKit."
  )
  .version("0.0.2");

program
  .command("init")
  .description("Install the Lumo skill into an AI coding assistant.")
  .option(
    "-a, --ai <client>",
    "Target client: claude | cursor | codex | generic (asks interactively if omitted)"
  )
  .option("--all", "Install into every supported client at once.")
  .option("--no-mcp", "Skip registering the MCP server (skill-only install).")
  .option("--dev", "Install from the current git clone instead of pip (for contributors).")
  .action(initCommand);

program
  .command("doctor")
  .description("Verify Python tools, MCP server, and skill installation paths.")
  .action(doctorCommand);

program
  .command("uninstall")
  .description("Remove the Lumo skill from an AI client (Python tools left intact).")
  .option("-a, --ai <client>", "Which client to remove from (asks interactively if omitted)")
  .option("--all", "Remove from every supported client at once.")
  .action(uninstallCommand);

program.parseAsync(process.argv).catch((err) => {
  console.error(kleur.red(`\n✗ ${err.message ?? err}`));
  process.exit(1);
});
