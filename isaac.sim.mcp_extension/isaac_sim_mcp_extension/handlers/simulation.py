# MIT License
#
# Copyright (c) 2023-2025 omni-mcp
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

"""Simulation control command handlers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from ..adapters.base import IsaacAdapterBase


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["simulation.play"] = lambda **p: play(adapter, **p)
    registry["simulation.pause"] = lambda **p: pause(adapter, **p)
    registry["simulation.stop"] = lambda **p: stop(adapter, **p)
    registry["simulation.step"] = lambda **p: step(adapter, **p)
    registry["simulation.set_physics"] = lambda **p: set_physics(adapter, **p)
    registry["simulation.execute_script"] = lambda **p: execute_script(adapter, **p)
    registry["simulation.get_state"] = lambda **p: get_simulation_state(adapter, **p)
    registry["simulation.get_logs"] = lambda **p: get_logs(adapter, **p)
    registry["simulation.get_physics_state"] = lambda **p: get_physics_state_handler(adapter, **p)
    registry["simulation.get_joint_config"] = lambda **p: get_joint_config_handler(adapter, **p)
    registry["simulation.reload_script"] = lambda **p: reload_script_handler(adapter, **p)


def play(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    try:
        adapter.play()
        return {"status": "success", "message": "Simulation started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def pause(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    try:
        adapter.pause()
        return {"status": "success", "message": "Simulation paused"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def stop(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    try:
        adapter.stop()
        return {"status": "success", "message": "Simulation stopped"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def step(adapter: IsaacAdapterBase, num_steps: int = 1) -> Dict[str, Any]:
    try:
        adapter.step(num_steps=num_steps)
        return {"status": "success", "message": f"Stepped {num_steps} frames"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_physics(adapter: IsaacAdapterBase, gravity: Optional[Sequence[float]] = None, time_step: Optional[float] = None, gpu_enabled: Optional[bool] = None) -> Dict[str, Any]:
    try:
        # Physics params are set via the PhysicsContext on the World
        # For now, gravity is the most common parameter
        if gravity is not None:
            adapter.create_physics_scene(gravity=gravity)
        return {"status": "success", "message": "Physics parameters updated"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def execute_script(adapter: IsaacAdapterBase, code: Optional[str] = None, cwd: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not code:
            return {"status": "error", "message": "code is required"}
        result = adapter.execute_script(code, cwd=cwd)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_simulation_state(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    try:
        result = adapter.get_simulation_state()
        return {"status": "success", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_physics_state_handler(adapter: IsaacAdapterBase, prim_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        result = adapter.get_physics_state(prim_path)
        return {"status": "success", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_joint_config_handler(adapter: IsaacAdapterBase, prim_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        result = adapter.get_joint_config(prim_path)
        return {"status": "success", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def reload_script_handler(adapter: IsaacAdapterBase, file_path: Optional[str] = None, module_name: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not file_path:
            return {"status": "error", "message": "file_path is required"}
        result = adapter.reload_script(file_path, module_name=module_name)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Log buffer for get_logs ───────────────────────────────────────────────────

_log_buffer: list = []
_log_listener_active: bool = False
_MAX_LOG_BUFFER = 500


def _ensure_log_listener():
    """Register a carb log listener that captures errors and warnings."""
    global _log_listener_active
    if _log_listener_active:
        return

    import carb
    import omni.log

    logger = omni.log.get_log()

    def _on_log(source, level, filename, function_name, line, message):
        if level >= omni.log.Level.WARN:
            level_name = "WARN" if level == omni.log.Level.WARN else "ERROR"
            entry = f"[{level_name}] [{source}] {message}"
            _log_buffer.append(entry)
            if len(_log_buffer) > _MAX_LOG_BUFFER:
                _log_buffer.pop(0)

    logger.set_channel_enabled("*", omni.log.SettingBehavior.OVERRIDE, True)
    logger.add_log_callback(_on_log)
    _log_listener_active = True


def get_logs(adapter: IsaacAdapterBase, clear: bool = True, count: int = 100) -> Dict[str, Any]:
    """Return recent warning/error log messages from the Isaac Sim console."""
    try:
        _ensure_log_listener()
        logs = _log_buffer[-count:]
        if clear:
            _log_buffer.clear()
        return {
            "status": "success",
            "log_count": len(logs),
            "logs": logs,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
