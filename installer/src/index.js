#!/usr/bin/env node
/**
 * lumo — mobile UI/UX design intelligence installer.
 *
 * Subcommands:
 *   init [--ai <client>] [--all] [--no-mcp] [--dev]
 *   doctor
 *   uninstall [--ai <client>] [--all]
 *
 * Supported AI clients in v0.1: claude, cursor, codex, generic.
 * Other clients can still consume Lumo via `npx skills add OneXeor-Dev/lumo`
 * or by pointing their MCP config at `lumo-mcp`.
 *
 * Argument parsing uses node:util parseArgs (Node ≥ 18.3) — zero external
 * dependencies, so Socket.dev sees nothing to flag at the dependency tree.
 */

import { parseArgs } from "node:util";

import { initCommand } from "./commands/init.js";
import { doctorCommand } from "./commands/doctor.js";
import { uninstallCommand } from "./commands/uninstall.js";
import { red } from "./lib/style.js";

const VERSION = "0.0.6";

const USAGE = `lumo — mobile UI/UX design intelligence installer (v${VERSION})

Usage:
  lumo init [options]         Install the Lumo skill into an AI coding assistant.
  lumo doctor                 Verify Python tools, MCP server, and skill paths.
  lumo uninstall [options]    Remove the Lumo skill from an AI client.
  lumo --help                 Show this message.
  lumo --version              Print the installer version.

init options:
  -a, --ai <client>           claude | cursor | codex | generic (asks if omitted)
      --all                   Install into every supported client at once.
      --no-mcp                Skip registering the MCP server (skill-only).
      --dev                   Install from the current git clone (contributors).

uninstall options:
  -a, --ai <client>           Which client to remove from (asks if omitted).
      --all                   Remove from every supported client at once.
`;

function parseFlags(argv) {
  // node:util parseArgs cannot do subcommands natively; we extract the
  // first positional ourselves, then run parseArgs on the rest.
  // parseArgs also doesn't recognise '--no-flag' as the negation of
  // 'flag', so we translate manually before passing it on.
  const [cmd, ...rawRest] = argv;
  let mcpExplicitlyOff = false;
  const rest = rawRest.filter((a) => {
    if (a === "--no-mcp") {
      mcpExplicitlyOff = true;
      return false;
    }
    return true;
  });

  const { values } = parseArgs({
    args: rest,
    allowPositionals: false,
    strict: true,
    options: {
      ai: { type: "string", short: "a" },
      all: { type: "boolean", default: false },
      mcp: { type: "boolean", default: true },
      dev: { type: "boolean", default: false },
      help: { type: "boolean", short: "h", default: false },
      version: { type: "boolean", short: "V", default: false },
    },
  });
  if (mcpExplicitlyOff) values.mcp = false;
  return { cmd, values };
}

async function main() {
  const argv = process.argv.slice(2);

  // No subcommand → top-level help / version.
  if (argv.length === 0 || argv[0] === "--help" || argv[0] === "-h") {
    process.stdout.write(USAGE);
    return 0;
  }
  if (argv[0] === "--version" || argv[0] === "-V") {
    process.stdout.write(`${VERSION}\n`);
    return 0;
  }

  let parsed;
  try {
    parsed = parseFlags(argv);
  } catch (err) {
    process.stderr.write(red(`✗ ${err.message ?? err}\n`));
    process.stderr.write("\nRun `lumo --help` for usage.\n");
    return 2;
  }

  const { cmd, values } = parsed;

  if (values.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  switch (cmd) {
    case "init":
      await initCommand(values);
      return 0;
    case "doctor":
      await doctorCommand();
      return 0;
    case "uninstall":
      await uninstallCommand(values);
      return 0;
    default:
      process.stderr.write(red(`✗ unknown subcommand: ${cmd}\n`));
      process.stderr.write("\nRun `lumo --help` for usage.\n");
      return 2;
  }
}

main()
  .then((code) => process.exit(code ?? 0))
  .catch((err) => {
    process.stderr.write(red(`\n✗ ${err.message ?? err}\n`));
    process.exit(1);
  });
