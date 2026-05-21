#!/usr/bin/env bash
# Demo script for recording with asciinema + demo-magic.
#
# This script runs photree commands against a deterministic
# environment. It is designed to be executed inside
# an asciinema recording session:
#
#   asciinema rec --command ./demo/demo.sh demo/demo.cast
#   agg demo/demo.cast demo/demo.gif
#
# Requirements:
#   pip install photree  # or: poetry install (dev)
#   brew install pv tree # for simulated typing + directory trees

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=demo-magic.sh
source "$SCRIPT_DIR/demo-magic.sh"

# Auto-advance (no ENTER required) for scripted recording
NO_WAIT=true
TYPE_SPEED=40
DEMO_COMMENT_COLOR=$CYAN

DEMO_DIR="/tmp/photree-demo"
GALLERY="$DEMO_DIR/gallery"
SHARE="$DEMO_DIR/share"

# Pause between commands so the viewer can read the output
pause() { sleep "${1:-2}"; }

# ── Setup ────────────────────────────────────────────────
rm -rf "$DEMO_DIR"

# On Linux (CI), create a fake sips shim that copies files instead of converting.
# This lets the demo run without macOS sips — JPEG output won't be real JPEG,
# but the demo doesn't assert file content.
if ! command -v sips &>/dev/null; then
    SIPS_SHIM_DIR="$DEMO_DIR/.shims"
    mkdir -p "$SIPS_SHIM_DIR"
    cat > "$SIPS_SHIM_DIR/sips" <<'SHIM'
#!/usr/bin/env bash
# Fake sips: parse --out <dst> from args and copy the source file
src="" dst=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --out) dst="$2"; shift 2 ;;
        -s)    shift 2 ;;  # skip -s format <fmt>
        *)     src="$1"; shift ;;
    esac
done
[[ -n "$src" && -n "$dst" ]] && cp "$src" "$dst"
SHIM
    chmod +x "$SIPS_SHIM_DIR/sips"
    export PATH="$SIPS_SHIM_DIR:$PATH"
fi

p "# Display photree version"
pe "photree --version"
pause

p "# Seed demo data"
pe "photree demo seed --base-dir $DEMO_DIR"
pause 3

p "# Show the demo directory structure"
pe "tree $DEMO_DIR"
pause 3

# ── Import ───────────────────────────────────────────────

ALBUM="$DEMO_DIR/2024-06-15 - Demo Album"
IC="$DEMO_DIR/image-capture"

p "# Browse the Image Capture source directory"
pe "ls \"$IC\""
pause 3

p "# Browse the album selection"
pe "ls \"$ALBUM/to-import\""
pause 3

p "# Go to the album directory"
pe "cd \"$ALBUM\""
cd "$ALBUM"

p "# Import from Image Capture"
pe "photree album import -s \"$IC\""
pause 3

p "# Browse the album after import"
pe "tree ."
pause 3

# ── Check ────────────────────────────────────────────────

p "# Check album integrity"
pe "photree album check"
pause 3

# ── Optimize ─────────────────────────────────────────────

p "# Optimize (replace copies with symlinks)"
pe "photree album optimize --link-mode symlink"
pause 3

p "# Verify integrity after optimization"
pe "photree album check"
pause 3

# ── Gallery ─────────────────────────────────────────────

p "# Initialize a gallery"
pe "mkdir -p \"$GALLERY\" && photree gallery init -d \"$GALLERY\" --link-mode symlink"
pause 3

p "# Import the album into the gallery"
pe "photree gallery import -a \"$ALBUM\" -g \"$GALLERY\""
pause 3

p "# Go to the gallery directory"
pe "cd \"$GALLERY\""
cd "$GALLERY"

p "# Show the gallery directory structure"
pe "tree ."
pause 3

p "# Check gallery integrity"
pe "photree gallery check"
pause 3

# ── Stats ───────────────────────────────────────────────

p "# Show gallery-wide statistics with per-year breakdown"
pe "photree gallery stats"
pause 3

# ── Export ───────────────────────────────────────────────

p "# Create a share directory with sentinel file"
pe "mkdir -p \"$SHARE\" && touch \"$SHARE/.photree-share\""
pause

p "# Export all gallery albums (main-only layout)"
pe "photree gallery export --share-dir \"$SHARE\" --album-layout main"
pause 3

p "# Show the exported albums"
pe "tree \"$SHARE\""
pause 3
