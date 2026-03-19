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
#   brew install pv      # for simulated typing

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=demo-magic.sh
source "$SCRIPT_DIR/demo-magic.sh"

# Auto-advance (no ENTER required) for scripted recording
NO_WAIT=true
TYPE_SPEED=40
DEMO_COMMENT_COLOR=$CYAN

# Pause between commands so the viewer can read the output
pause() { sleep "${1:-2}"; }

# ── Demo ────────────────────────────────────────────────

p "# Display photree version"
pe "photree --version"
pause
