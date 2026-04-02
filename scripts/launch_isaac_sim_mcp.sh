#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAACSIM_ROOT="${ISAACSIM_ROOT:-$HOME/isaacsim}"
ISAAC_SIM_SH="$ISAACSIM_ROOT/isaac-sim.sh"
EXTENSION_TOML="$REPO_ROOT/isaac.sim.mcp_extension/config/extension.toml"
EXTENSION_ID="isaac.sim.mcp_extension"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/logs"
MCP_BASE_PORT=${ISAAC_MCP_PORT:-8766}
MCP_MAX_PORT=$((MCP_BASE_PORT + 100))
MCP_WAIT_TIMEOUT=120   # seconds to wait for the extension socket

mkdir -p "$LOG_DIR"

# --- Validate paths ---
if [[ ! -x "$ISAAC_SIM_SH" ]]; then
  notify-send "Isaac Sim MCP" "Isaac Sim not found at: $ISAAC_SIM_SH\nSet ISAACSIM_ROOT and try again." 2>/dev/null || true
  echo "Error: Isaac Sim launcher not found at: $ISAAC_SIM_SH" >&2
  exit 1
fi

if [[ ! -f "$EXTENSION_TOML" ]]; then
  notify-send "Isaac Sim MCP" "Extension manifest not found at: $EXTENSION_TOML" 2>/dev/null || true
  echo "Error: extension manifest not found at: $EXTENSION_TOML" >&2
  exit 1
fi

# --- Find a free port ---
find_free_port() {
  local port=$1
  local max_port=$2
  while (( port <= max_port )); do
    if ! ss -tln 2>/dev/null | grep -q ":${port} " && \
       ! nc -z localhost "$port" 2>/dev/null; then
      echo "$port"
      return 0
    fi
    port=$((port + 1))
  done
  return 1
}

MCP_PORT=$(find_free_port "$MCP_BASE_PORT" "$MCP_MAX_PORT") || {
  echo "Error: No free port found in range $MCP_BASE_PORT-$MCP_MAX_PORT." >&2
  notify-send "Isaac Sim MCP" "No free port found in range $MCP_BASE_PORT-$MCP_MAX_PORT." 2>/dev/null || true
  exit 1
}
echo "Using port $MCP_PORT for this instance."

# --- Cleanup on exit ---
ISAAC_PID=""
MCP_PID=""

cleanup() {
  if [[ -n "$MCP_PID" ]] && kill -0 "$MCP_PID" 2>/dev/null; then
    echo "Stopping MCP server (PID: $MCP_PID, port: $MCP_PORT)..."
    kill "$MCP_PID" 2>/dev/null || true
    wait "$MCP_PID" 2>/dev/null || true
  fi
  if [[ -n "$ISAAC_PID" ]] && kill -0 "$ISAAC_PID" 2>/dev/null; then
    echo "Stopping Isaac Sim (PID: $ISAAC_PID)..."
    kill "$ISAAC_PID" 2>/dev/null || true
    wait "$ISAAC_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# --- Launch Isaac Sim in background with the chosen port ---
echo "Launching Isaac Sim with MCP extension on port $MCP_PORT..."
"$ISAAC_SIM_SH" \
  --ext-folder "$REPO_ROOT" \
  --enable "$EXTENSION_ID" \
  --/exts/isaac.sim.mcp/server.port="$MCP_PORT" \
  "$@" &
ISAAC_PID=$!
echo "Isaac Sim started (PID: $ISAAC_PID)"

# --- Wait for the extension socket to be ready ---
echo "Waiting for MCP extension socket on port $MCP_PORT (timeout: ${MCP_WAIT_TIMEOUT}s)..."
elapsed=0
while ! ss -tln 2>/dev/null | grep -q ":${MCP_PORT} " && \
      ! nc -z localhost "$MCP_PORT" 2>/dev/null; do
  if ! kill -0 "$ISAAC_PID" 2>/dev/null; then
    echo "Error: Isaac Sim exited before the extension socket was ready." >&2
    exit 1
  fi
  if (( elapsed >= MCP_WAIT_TIMEOUT )); then
    echo "Error: Timed out waiting for extension socket on port $MCP_PORT." >&2
    exit 1
  fi
  sleep 2
  elapsed=$((elapsed + 2))
  echo "  ... waiting ($elapsed/${MCP_WAIT_TIMEOUT}s)"
done
echo "Extension socket is ready on port $MCP_PORT."

# --- Start MCP server with the same port ---
INSTALLED_CLI="$REPO_ROOT/.venv/bin/isaacsim-mcp-server"

if [[ -x "$INSTALLED_CLI" ]]; then
  echo "Starting MCP server on port $MCP_PORT (installed package)..."
  ISAAC_MCP_PORT="$MCP_PORT" "$INSTALLED_CLI" \
    > "$LOG_DIR/mcp_server_${MCP_PORT}.log" 2>&1 &
  MCP_PID=$!
  echo "MCP server started (PID: $MCP_PID)"
elif [[ -x "$PYTHON_BIN" && -f "$REPO_ROOT/isaac_mcp/server.py" ]]; then
  echo "Starting MCP server on port $MCP_PORT (from source)..."
  cd "$REPO_ROOT"
  ISAAC_MCP_PORT="$MCP_PORT" "$PYTHON_BIN" -m isaac_mcp.server \
    > "$LOG_DIR/mcp_server_${MCP_PORT}.log" 2>&1 &
  MCP_PID=$!
  echo "MCP server started (PID: $MCP_PID)"
else
  echo "Warning: MCP server not found. Skipping MCP server." >&2
  echo "Install via: pip install isaacsim-mcp-server" >&2
  echo "Or run: ./scripts/setup_python_env.sh" >&2
fi

# --- Wait for Isaac Sim to exit ---
wait "$ISAAC_PID"
