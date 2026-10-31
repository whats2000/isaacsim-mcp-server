# MIT License
#
# Copyright (c) 2023-2025 omni-mcp
# Copyright (c) 2026 whats2000
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Isaac Sim MCP Extension — slim entry point.

Routes incoming socket commands to handler modules via a registry.
"""

from __future__ import annotations

import gc
import os
import sys
import traceback
from typing import Any, Dict, Optional

import carb
import omni.ext
import omni.usd

from .adapters import get_adapter
from .handlers import register_all_handlers
from .socket_server import SocketServer

# Under the extension's own settings root, which Kit also uses for the manifest.
_LIVE_VIEW_SETTINGS = "/exts/isaac.sim.mcp_extension/live_view"
_LIVE_VIEW_PORT_OFFSET = 9434  # the default MCP port 8766 serves the live view on 18200


def _env_int(name: str) -> Optional[int]:
    """Read an int from the environment, ignoring unset or malformed values."""
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        carb.log_warn(f"Ignoring non-integer {name}={raw!r}")
        return None


def _resolve_endpoint(settings: Any) -> tuple[str, int]:
    """Resolve the socket (host, port) from Kit settings and the environment.

    First hit wins. The legacy ``/exts/isaac.sim.mcp/`` prefix is read first
    because the launcher scripts pass it explicitly on the Kit command line.
    Kit itself populates the manifest ``[settings]`` block under the extension
    folder name, ``/exts/isaac.sim.mcp_extension/`` (with the port under
    ``server.socket``), so those are read next, then the ISAAC_MCP_PORT /
    ISAAC_MCP_HOST environment variables, then the built-in defaults.
    """
    port = (
        settings.get("/exts/isaac.sim.mcp/server.port")
        or settings.get("/exts/isaac.sim.mcp_extension/server.port")
        or settings.get("/exts/isaac.sim.mcp_extension/server.socket")
        or _env_int("ISAAC_MCP_PORT")
        or 8766
    )
    host = (
        settings.get("/exts/isaac.sim.mcp/server.host")
        or settings.get("/exts/isaac.sim.mcp_extension/server.host")
        or os.environ.get("ISAAC_MCP_HOST")
        or "localhost"
    )
    return host, port


def _live_view_enabled(settings: Any) -> bool:
    """The live view is opt-in: --live-view (a Kit setting) or ISAAC_LIVE_VIEW=1."""
    if settings.get(f"{_LIVE_VIEW_SETTINGS}/enabled"):
        return True
    return os.environ.get("ISAAC_LIVE_VIEW", "").lower() in ("1", "true")


def _resolve_live_view_endpoint(settings: Any, mcp_port: int) -> tuple[str, int]:
    """Resolve the live view (host, port). First hit wins, as in _resolve_endpoint.

    The default port follows the MCP port, so instances that launch_isaac_sim_mcp.sh
    auto-assigns different MCP ports do not fight over one live view port.
    """
    port = (
        settings.get(f"{_LIVE_VIEW_SETTINGS}/port")
        or _env_int("ISAAC_LIVE_VIEW_PORT")
        or mcp_port + _LIVE_VIEW_PORT_OFFSET
    )
    host = settings.get(f"{_LIVE_VIEW_SETTINGS}/host") or os.environ.get("ISAAC_LIVE_VIEW_HOST") or "127.0.0.1"
    return host, port


def _start_live_view(settings: Any, mcp_port: int) -> None:
    """Start the live view if opted in. A failure here must not cost the MCP socket."""
    if not _live_view_enabled(settings):
        return
    host, port = _resolve_live_view_endpoint(settings, mcp_port)
    try:
        from . import live_view

        live_view.start(port, host)
    except Exception as e:
        carb.log_error(f"[live_view] could not start on {host}:{port}: {e}. Set ISAAC_LIVE_VIEW_PORT to another port.")


class MCPExtension(omni.ext.IExt):
    def __init__(self):
        super().__init__()
        self.ext_id = None
        self._settings = carb.settings.get_settings()
        self._registry: Dict[str, Any] = {}
        self._adapter = None
        self._server: SocketServer | None = None
        self._play_sub = None

    def on_startup(self, ext_id: str) -> None:
        print("trigger  on_startup for: ", ext_id)
        self.ext_id = ext_id
        host, port = _resolve_endpoint(self._settings)

        self._adapter = get_adapter()
        register_all_handlers(self._registry, self._adapter)
        print(f"Registered {len(self._registry)} command handlers")

        # Capture logs from extension load so early diagnostics are not missed,
        # and mark a run boundary on each timeline Play so get_isaac_logs can
        # scope to the current run.
        try:
            import omni.timeline

            from .handlers.simulation import _ensure_log_listener, mark_play_boundary

            _ensure_log_listener()
            self._play_sub = (
                omni.timeline.get_timeline_interface()
                .get_timeline_event_stream()
                .create_subscription_to_pop_by_type(
                    int(omni.timeline.TimelineEventType.PLAY),
                    lambda _e: mark_play_boundary(),
                )
            )
        except Exception as _e:
            print("log listener / play-boundary setup skipped:", _e)

        self._server = SocketServer(host, port, self._execute_command)
        self._server.start()
        _start_live_view(self._settings, port)

    def on_shutdown(self) -> None:
        print("trigger  on_shutdown for: ", self.ext_id)
        # Only imported when it was used, so a run that never opted in loads none of it.
        live_view = sys.modules.get(f"{__package__}.live_view")
        if live_view:
            live_view.stop()
        if self._server:
            self._server.stop()
        self._play_sub = None
        self._registry.clear()
        gc.collect()

    # ── Command routing ────────────────────────────────────────────────────────

    def _stage_pending(self) -> bool:
        """True while Kit has started this extension but has no stage yet.

        The socket starts accepting connections roughly 8 seconds before the
        stage exists (measured on 6.0.1: connections at t+6.8s, first successful
        stage read at t+14.5s). An MCP client normally connects the moment the
        port opens, so an agent's opening commands land in that window and every
        stage-dependent handler failed with a bare
        "'NoneType' object has no attribute 'GetPrimAtPath'" — which reads as a
        broken server rather than one that is still starting.
        """
        try:
            return self._adapter.get_stage() is None
        except Exception:
            # A runtime that cannot answer at all is not "pending"; let the
            # handler run and report its own, more specific failure.
            return False

    def _execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        cmd_type = command.get("type", "")
        params = command.get("params", {})
        handler = self._registry.get(cmd_type)
        if handler and self._stage_pending():
            return {
                "status": "error",
                "message": (
                    "Isaac Sim is still starting up — no stage yet. This clears on its own a "
                    "few seconds after the window appears; retry the same command."
                ),
            }
        if handler:
            try:
                result = handler(**params)
                if result and result.get("status") == "success":
                    return {"status": "success", "result": result}
                else:
                    if not result:
                        return {"status": "error", "message": "No result"}
                    # Forward whatever else the handler attached, not just the
                    # message. An error that carries the next step is what lets
                    # a caller recover on its own: create_lidar refuses a
                    # poisoned prim path and offers `suggested_prim_path`, and
                    # dropping it here meant the client saw None and had to
                    # invent a path from prose. Handler tests call the function
                    # directly and cannot catch this — it only shows on a round
                    # trip through the extension.
                    error = {"status": "error", "message": result.get("message", "Unknown error")}
                    error.update({k: v for k, v in result.items() if k not in ("status", "message")})
                    return error
            except Exception as e:
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": f"Unknown command: {cmd_type}"}
