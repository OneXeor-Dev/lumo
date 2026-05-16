# VHS tape: rebuild with `vhs assets/demo.tape` from the repo root.

Output assets/demo.gif

Set FontSize 14
Set Width 1100
Set Height 700
Set Theme "Dracula"
Set TypingSpeed 30ms
Set PlaybackSpeed 1.0

# Activate the project venv so the lumo-* binaries are on PATH.
Hide
Type "cd tools && source .venv/bin/activate && clear" Enter
Sleep 200ms
Show

# --- lumo-wcag --------------------------------------------------------------

Type "# WCAG: classic Tailwind blue-500 on white — junior assumes it passes." Enter
Sleep 500ms
Type "lumo-wcag check --fg '#3B82F6' --bg '#FFFFFF'" Enter
Sleep 2s

Type "# Now auto-correct in OKLCH while preserving brand chroma + hue." Enter
Sleep 500ms
Type "lumo-wcag fix --fg '#7DD3FC' --bg '#FFFFFF'" Enter
Sleep 2500ms

# --- lumo-parity ------------------------------------------------------------

Type "clear" Enter
Sleep 300ms
Type "# Cross-platform parity: someone wrote padding(48) in SwiftUI" Enter
Type "# thinking 'iOS uses 3× because Retina'. It doesn't." Enter
Sleep 800ms
Type "lumo-parity diff \\" Enter
Type "  --android ../examples/parity_android.json \\" Enter
Type "  --ios     ../examples/parity_ios.json \\" Enter
Type "  --config  ../examples/lumo.config.json" Enter
Sleep 4500ms

# --- lumo-theory ------------------------------------------------------------

Type "clear" Enter
Sleep 300ms
Type "# Theory: Fitts + Hick + reach. Bad layout: 32dp icon, primary in" Enter
Type "# top corner, 7 equal-weight nav items." Enter
Sleep 800ms
Type "lumo-theory check --layout ../examples/theory_bad_layout.json" Enter
Sleep 5s

Sleep 1s
