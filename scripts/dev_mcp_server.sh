#!/usr/bin/env bash
set -euo pipefail

# ── Dev MCP Server ────────────────────────────────────────────────────────────
# Development wrapper for the MCP server with extension hot-reloading.
#
# Use this in place of run_mcp_server.sh during development. It:
#   1. Waits for the Isaac Sim extension socket to be ready
#   2. Hot-reloads extension handlers inside the running Isaac Sim
#      (picks up code changes without restarting Isaac Sim)
#   3. Starts a background watcher that hot-reloads the extension whenever
#      files in isaac.sim.mcp_extension/ change on disk
#   4. Runs the MCP server (connected to the IDE via stdio)
#
# Usage:
#   Point your MCP client at this script instead of run_mcp_server.sh:
#
#   Claude Code CLI:
#     claude mcp add isaac-sim-dev /path/to/scripts/dev_mcp_server.sh
#
#   .vscode/mcp.json:
#     { "servers": { "isaac-sim": { "command": "/path/to/scripts/dev_mcp_server.sh" } } }
#
#   ISAAC_MCP_PORT=8767 ./scripts/dev_mcp_server.sh   # use a different port
#
# Prerequisites:
#   - Isaac Sim running with the MCP extension enabled
#   - Python venv set up (./scripts/setup_python_env.sh)
# ──────────────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
MCP_PORT="${ISAAC_MCP_PORT:-8766}"
MCP_HOST="localhost"
POLL_INTERVAL="${DEV_POLL_INTERVAL:-2}"

EXTENSION_DIR="$REPO_ROOT/isaac.sim.mcp_extension/isaac_sim_mcp_extension"

# ── Validate ──────────────────────────────────────────────────────────────────

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: Python venv not found at $PYTHON_BIN" >&2
  echo "Run ./scripts/setup_python_env.sh first." >&2
  exit 1
fi

if [[ ! -f "$REPO_ROOT/isaac_mcp/server.py" ]]; then
  echo "Error: MCP server module not found at $REPO_ROOT/isaac_mcp/server.py" >&2
  exit 1
fi

# ── Helpers ───────────────────────────────────────────────────────────────────

# All dev output goes to stderr so it doesn't interfere with MCP stdio
log() { echo "[dev] $*" >&2; }

wait_for_extension_socket() {
  local elapsed=0
  local timeout=120
  while ! nc -z "$MCP_HOST" "$MCP_PORT" 2>/dev/null; do
    if (( elapsed >= timeout )); then
      log "Error: Timed out waiting for extension socket on port $MCP_PORT."
      log "Make sure Isaac Sim is running with the MCP extension enabled."
      exit 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
}

# Clear stale .pyc files so importlib.reload() picks up the latest source.
clear_pyc() {
  find "$EXTENSION_DIR" -name '*.pyc' -delete 2>/dev/null
  find "$EXTENSION_DIR" -name '__pycache__' -type d -empty -delete 2>/dev/null
}

# Send execute_script to Isaac Sim extension to reload handler modules in-place.
hot_reload_extension() {
  clear_pyc
  "$PYTHON_BIN" -c "
import socket, json, sys

reload_code = '''
import importlib, os, glob

# Clear stale .pyc for ALL loaded isaac_sim_mcp_extension modules so
# importlib.reload() picks up the latest source.
for mod_name, mod in list(__import__("sys").modules.items()):
    if mod_name.startswith("isaac_sim_mcp_extension"):
        src = getattr(mod, "__file__", None)
        if src and src.endswith(".py"):
            cache_dir = os.path.join(os.path.dirname(src), "__pycache__")
            base = os.path.splitext(os.path.basename(src))[0]
            for pyc in glob.glob(os.path.join(cache_dir, base + ".*.pyc")):
                try:
                    os.remove(pyc)
                except OSError:
                    pass
importlib.invalidate_caches()

import isaac_sim_mcp_extension.adapters.base as base_mod
import isaac_sim_mcp_extension.adapters.v5 as v5_mod
import isaac_sim_mcp_extension.adapters as adapters_init
import isaac_sim_mcp_extension.handlers.robots as robots_mod
import isaac_sim_mcp_extension.handlers.scene as scene_mod
import isaac_sim_mcp_extension.handlers.objects as objects_mod
import isaac_sim_mcp_extension.handlers.assets as assets_mod
import isaac_sim_mcp_extension.handlers.simulation as simulation_mod
import isaac_sim_mcp_extension.handlers.sensors as sensors_mod
import isaac_sim_mcp_extension.handlers.materials as materials_mod
import isaac_sim_mcp_extension.handlers.lighting as lighting_mod
import isaac_sim_mcp_extension.handlers.graphs as graphs_mod
import isaac_sim_mcp_extension.handlers as handlers_init

# Reload adapter layer first, then handlers, then __init__ modules
importlib.reload(base_mod)
importlib.reload(v5_mod)
importlib.reload(adapters_init)
importlib.reload(robots_mod)
importlib.reload(scene_mod)
importlib.reload(objects_mod)
importlib.reload(assets_mod)
importlib.reload(simulation_mod)
importlib.reload(sensors_mod)
importlib.reload(materials_mod)
importlib.reload(lighting_mod)
importlib.reload(graphs_mod)
importlib.reload(handlers_init)

# Re-register all handlers with a fresh adapter
from isaac_sim_mcp_extension.adapters import get_adapter
from isaac_sim_mcp_extension.handlers import register_all_handlers

import gc
from isaac_sim_mcp_extension.extension import MCPExtension
for obj in gc.get_objects():
    if isinstance(obj, MCPExtension):
        adapter = get_adapter()
        # Use __dict__ to bypass pybind11 __setattr__ on omni.ext.IExt subclasses
        obj.__dict__[\"_adapter\"] = adapter
        obj._registry.clear()
        register_all_handlers(obj._registry, adapter)

        # Wrap reload_script to clear stale .pyc before importlib.reload()
        _orig_reload = adapter.reload_script
        def _patched_reload(file_path, module_name=None, _orig=_orig_reload):
            import importlib as _il, os as _os, glob as _gl, sys as _sys
            if module_name and module_name in _sys.modules:
                src = getattr(_sys.modules[module_name], \"__file__\", None)
                if src and src.endswith(\".py\"):
                    cache_dir = _os.path.join(_os.path.dirname(src), \"__pycache__\")
                    base = _os.path.splitext(_os.path.basename(src))[0]
                    for pyc in _gl.glob(_os.path.join(cache_dir, base + \".*.pyc\")):
                        try:
                            _os.remove(pyc)
                        except OSError:
                            pass
                _il.invalidate_caches()
            elif file_path:
                abs_path = _os.path.abspath(file_path)
                if abs_path.endswith(\".py\"):
                    cache_dir = _os.path.join(_os.path.dirname(abs_path), \"__pycache__\")
                    base = _os.path.splitext(_os.path.basename(abs_path))[0]
                    for pyc in _gl.glob(_os.path.join(cache_dir, base + \".*.pyc\")):
                        try:
                            _os.remove(pyc)
                        except OSError:
                            pass
                    _il.invalidate_caches()
            return _orig(file_path, module_name=module_name)
        adapter.reload_script = _patched_reload

        print(f\"Hot-reloaded {len(obj._registry)} handlers\")
        break
else:
    print(\"WARNING: Could not find MCPExtension instance for hot-reload\")
'''

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(30)
try:
    sock.connect(('$MCP_HOST', $MCP_PORT))
    cmd = json.dumps({'type': 'simulation.execute_script', 'params': {'code': reload_code}})
    sock.sendall(cmd.encode('utf-8'))
    chunks = []
    while True:
        chunk = sock.recv(16384)
        if not chunk:
            break
        chunks.append(chunk)
        try:
            data = b''.join(chunks)
            resp = json.loads(data.decode('utf-8'))
            status = resp.get('status', 'unknown')
            result = resp.get('result', resp.get('message', ''))
            if status == 'success':
                print('Extension hot-reload: OK', file=sys.stderr)
            else:
                print(f'Extension hot-reload issue: {result}', file=sys.stderr)
            break
        except json.JSONDecodeError:
            continue
finally:
    sock.close()
" 2>&1 >&2 || log "Warning: hot-reload failed (Isaac Sim may need a restart)"
}

# mtime-based fingerprint of all .py files in a directory
dir_fingerprint() {
  find "$1" -name '*.py' -printf '%T@:%p\n' 2>/dev/null | sort | md5sum | awk '{print $1}'
}

# Background watcher — hot-reloads extension when files change on disk.
# Runs in a subshell so it dies when the main process (MCP server) exits.
start_extension_watcher() {
  (
    local prev_fp
    prev_fp="$(dir_fingerprint "$EXTENSION_DIR")"

    while true; do
      sleep "$POLL_INTERVAL"
      local cur_fp
      cur_fp="$(dir_fingerprint "$EXTENSION_DIR")"
      if [[ "$cur_fp" != "$prev_fp" ]]; then
        log "Extension code changed — hot-reloading..."
        hot_reload_extension
        prev_fp="$cur_fp"
      fi
    done
  ) &
  WATCHER_PID=$!
  trap "kill $WATCHER_PID 2>/dev/null; wait $WATCHER_PID 2>/dev/null" EXIT
}

# ── Main ──────────────────────────────────────────────────────────────────────

log "Isaac Sim MCP — Dev Server"
log "Port: $MCP_PORT | Watching: isaac.sim.mcp_extension/"
log ""

# 1. Wait for Isaac Sim
log "Waiting for extension socket on $MCP_HOST:$MCP_PORT..."
wait_for_extension_socket
log "Extension socket ready."

# 2. Hot-reload extension to pick up latest code from disk
log "Hot-reloading extension handlers..."
hot_reload_extension

# 3. Start background watcher for ongoing changes
start_extension_watcher
log "File watcher started (poll every ${POLL_INTERVAL}s)."
log "Launching MCP server..."
log ""

# 4. Exec into the MCP server — stdio goes to the IDE
cd "$REPO_ROOT"
exec env ISAAC_MCP_PORT="$MCP_PORT" "$PYTHON_BIN" -m isaac_mcp.server "$@"
