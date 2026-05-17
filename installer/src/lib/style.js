/**
 * Tiny ANSI styling helper. Self-contained replacement for `kleur`.
 *
 * Why: Socket.dev flags packages whose dependency tree contains
 * environment-variable access (kleur reads NO_COLOR / FORCE_COLOR
 * which is legitimate but raises a supply-chain risk signal). We use
 * exactly four colours in the installer; rolling our own keeps
 * `dependencies: {}` empty.
 *
 * Colours are emitted unconditionally. If you need NO_COLOR support
 * later, gate the prefix strings on `process.env.NO_COLOR` here in
 * one place.
 */

const ESC = "\x1b";

function wrap(open, close) {
  return (text) => `${ESC}[${open}m${text}${ESC}[${close}m`;
}

export const cyan = wrap(36, 39);
export const green = wrap(32, 39);
export const yellow = wrap(33, 39);
export const red = wrap(31, 39);
export const dim = wrap(2, 22);
export const bold = wrap(1, 22);

/** Compose: `bold(cyan("text"))` works because every fn is `text -> text`. */
