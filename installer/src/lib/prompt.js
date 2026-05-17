/**
 * Tiny terminal `select` prompt. Self-contained replacement for `prompts`.
 *
 * Why: Socket.dev flagged `prompts` because it depends on `sisteransi`
 * which hasn't been updated in 5+ years (Maintenance alert). Our usage
 * is one select-from-list prompt; rolling our own keeps the package
 * dependency tree empty and removes the unmaintained-transitive alert.
 *
 * Renders a numbered list, waits for one keystroke or a typed number
 * followed by Enter. Plays well with raw-mode TTY. Falls back to
 * answer 0 (first option) when stdin is not a TTY (CI, piping).
 *
 * Returns the value of the chosen option, or undefined if the user
 * aborted with Ctrl-C / Ctrl-D / Esc.
 */

import readline from "node:readline";

import { bold, cyan, dim } from "./style.js";

/**
 * @typedef {object} Choice
 * @property {string} title
 * @property {any} value
 */

/**
 * @param {object} opts
 * @param {string} opts.message
 * @param {Choice[]} opts.choices
 * @param {number} [opts.initial]
 * @returns {Promise<any | undefined>}
 */
export function select({ message, choices, initial = 0 }) {
  return new Promise((resolve) => {
    const stdout = process.stdout;
    const stdin = process.stdin;

    // Non-interactive: pick the initial choice and move on.
    if (!stdin.isTTY) {
      stdout.write(`${cyan("?")} ${message} ${dim(`(non-interactive, picking ${choices[initial].title})`)}\n`);
      resolve(choices[initial].value);
      return;
    }

    stdout.write(`${cyan("?")} ${bold(message)}\n`);
    for (let i = 0; i < choices.length; i++) {
      const marker = i === initial ? cyan("›") : " ";
      stdout.write(`  ${marker} ${i + 1}. ${choices[i].title}\n`);
    }
    stdout.write(dim(`  (use 1-${choices.length} then Enter, or Ctrl-C to abort)\n`));

    const rl = readline.createInterface({
      input: stdin,
      output: stdout,
      terminal: true,
    });

    rl.question("> ", (raw) => {
      rl.close();
      const trimmed = raw.trim();
      if (trimmed === "") {
        resolve(choices[initial].value);
        return;
      }
      const idx = Number.parseInt(trimmed, 10) - 1;
      if (!Number.isInteger(idx) || idx < 0 || idx >= choices.length) {
        resolve(undefined);
        return;
      }
      resolve(choices[idx].value);
    });

    rl.on("SIGINT", () => {
      rl.close();
      resolve(undefined);
    });
  });
}
