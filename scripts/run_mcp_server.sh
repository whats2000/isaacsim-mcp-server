#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: Python environment not found at: $PYTHON_BIN" >&2
  echo "Run ./scripts/setup_python_env.sh first." >&2
  exit 1
fi

if [[ ! -f "$REPO_ROOT/isaac_mcp/server.py" ]]; then
  echo "Error: MCP server module not found at: $REPO_ROOT/isaac_mcp/server.py" >&2
  exit 1
fi

cd "$REPO_ROOT"
exec "$PYTHON_BIN" -m isaac_mcp.server "$@"
