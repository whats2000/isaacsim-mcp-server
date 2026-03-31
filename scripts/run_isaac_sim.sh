#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAACSIM_ROOT="${ISAACSIM_ROOT:-$HOME/isaacsim}"
ISAAC_SIM_SH="$ISAACSIM_ROOT/isaac-sim.sh"
EXTENSION_TOML="$REPO_ROOT/isaac.sim.mcp_extension/config/extension.toml"
EXTENSION_ID="isaac.sim.mcp_extension"

if [[ ! -x "$ISAAC_SIM_SH" ]]; then
  echo "Error: Isaac Sim launcher not found at: $ISAAC_SIM_SH" >&2
  echo "Set ISAACSIM_ROOT to your Isaac Sim install directory and try again." >&2
  exit 1
fi

if [[ ! -f "$EXTENSION_TOML" ]]; then
  echo "Error: extension manifest not found at: $EXTENSION_TOML" >&2
  echo "Run this script from inside the isaac-sim-mcp checkout." >&2
  exit 1
fi

echo "Repo root: $REPO_ROOT"
echo "Isaac Sim: $ISAAC_SIM_SH"
echo "Extension: $EXTENSION_ID"

exec "$ISAAC_SIM_SH" \
  --ext-folder "$REPO_ROOT" \
  --enable "$EXTENSION_ID" \
  "$@"
