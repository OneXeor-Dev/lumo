#!/usr/bin/env bash
# Maintainer-only: bundle the skill and publish to npm.
#
# We used to wire `bundle-skill` into the npm `prepack` lifecycle hook
# so `npm publish` would automatically copy /skill into installer/skill
# before packing. Socket.dev (and other supply-chain scanners) flag
# packages with ANY lifecycle script — even one that only runs on the
# maintainer's machine — because in principle a malicious package could
# put attacker code in `prepack` / `postinstall` etc.
#
# To keep our Supply Chain Security score clean we removed the
# lifecycle hook. The same bundling now happens here, as an explicit
# step the maintainer runs.
#
# Usage:
#   bash installer/scripts/release.sh           # bundle, pack, publish
#   bash installer/scripts/release.sh --dry-run # bundle and pack only

set -euo pipefail

cd "$(dirname "$0")/.."

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

echo "→ bundling /skill into installer/skill ..."
node scripts/bundle-skill.js

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "→ dry-run: npm pack --dry-run"
  npm pack --dry-run
  exit 0
fi

echo "→ publishing to npm ..."
npm publish --access public

echo
echo "✓ published. verify at https://www.npmjs.com/package/@onexeor/lumo"
