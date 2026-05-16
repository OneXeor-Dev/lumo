#!/usr/bin/env bash
# Rebuild assets/demo.cast and assets/demo.gif from real CLI output.
#
# Requires:
#   brew install asciinema agg
#   tools/.venv set up with `pip install -e ".[dev]"`
#
# Run from the repo root:
#   bash assets/record-demo.sh
#
# How it works: instead of recording an interactive TTY (which breaks
# in headless / non-interactive shells), we capture each CLI's real
# stdout once via subprocess and stitch together an asciicast v2 file
# with deterministic timings. Same output as a live recording, no
# flaky TTY.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Activate venv so lumo-* binaries are on PATH.
# shellcheck source=/dev/null
source tools/.venv/bin/activate

CAST="$REPO_ROOT/assets/demo.cast"
GIF="$REPO_ROOT/assets/demo.gif"

python3 - <<'PY'
import json
import os
import subprocess
import time
from pathlib import Path

REPO = Path(os.environ.get("REPO_ROOT") or os.getcwd())
CAST = REPO / "assets" / "demo.cast"

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO).stdout

wcag = run(["lumo-wcag", "fix", "--fg", "#7DD3FC", "--bg", "#FFFFFF"])
parity = run([
    "lumo-parity", "diff",
    "--android", "examples/parity_android.json",
    "--ios", "examples/parity_ios.json",
    "--config", "examples/lumo.config.json",
])
theory = run(["lumo-theory", "check", "--layout", "examples/theory_bad_layout.json"])

header = {
    "version": 2,
    "width": 110,
    "height": 36,
    "timestamp": int(time.time()),
    "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"},
}

state = {"t": 0.0}
events = []

ESC = "\x1b"

def emit(text, dt=0.04):
    for ch in text:
        events.append([round(state["t"], 3), "o", ch])
        state["t"] += dt

def pause(secs):
    state["t"] += secs

def line(prompt, cmd, output, wait_before=0.5, wait_after=1.5):
    emit(f"{ESC}[1;36m{prompt}{ESC}[0m ", dt=0.0)
    emit(cmd, dt=0.025)
    emit("\r\n", dt=0.0)
    pause(wait_before)
    for ln in output.splitlines(keepends=True):
        events.append([round(state["t"], 3), "o", ln.replace("\n", "\r\n")])
        state["t"] += 0.04
    pause(wait_after)

def banner(msg):
    emit(f"{ESC}[1;35m{msg}{ESC}[0m\r\n", dt=0.0)
    pause(0.6)

emit(f"{ESC}[2J{ESC}[H", dt=0.0)
banner("# Lumo — deterministic mobile UI/UX checks for AI coding assistants.")
pause(0.8)

banner("# 1. WCAG with OKLCH auto-correct — preserves brand hue + chroma.")
line("$", "lumo-wcag fix --fg '#7DD3FC' --bg '#FFFFFF'", wcag, wait_after=2.5)

banner("# 2. Cross-platform parity — catches the 16dp / 48pt junior bug.")
line(
    "$",
    "lumo-parity diff --android examples/parity_android.json --ios examples/parity_ios.json --config examples/lumo.config.json",
    parity,
    wait_after=4.0,
)

banner("# 3. Cognitive-science layout checks — Fitts, Hick, Gestalt, reach.")
line("$", "lumo-theory check --layout examples/theory_bad_layout.json", theory, wait_after=5.0)

with CAST.open("w") as f:
    f.write(json.dumps(header) + "\n")
    for ev in events:
        f.write(json.dumps(ev) + "\n")

print(f"wrote {CAST}: {len(events)} events, duration {state['t']:.1f}s")
PY

agg --cols 110 --rows 36 --theme monokai --speed 1.4 "$CAST" "$GIF"

echo
echo "✓ demo.cast → $CAST"
echo "✓ demo.gif  → $GIF"
