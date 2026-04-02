#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
INSTALLED_CLI="$REPO_ROOT/.venv/bin/isaacsim-mcp-server"

# Prefer the installed CLI entry point (pip install isaacsim-mcp-server)
if [[ -x "$INSTALLED_CLI" ]]; then
  exec env ISAAC_MCP_PORT="${ISAAC_MCP_PORT:-8766}" "$INSTALLED_CLI" "$@"
fi

# Fall back to running from source
if [[ -x "$PYTHON_BIN" && -f "$REPO_ROOT/isaac_mcp/server.py" ]]; then
  cd "$REPO_ROOT"
  exec "$PYTHON_BIN" -m isaac_mcp.server "$@"
fi

echo "Error: isaacsim-mcp-server not found." >&2
echo "Install via: pip install isaacsim-mcp-server" >&2
echo "Or run: ./scripts/setup_python_env.sh" >&2
exit 1
