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

"""Simulation control MCP tools."""

import json
from typing import Callable, List, Optional, TYPE_CHECKING
from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from isaac_mcp.connection import IsaacConnection


def register_tools(mcp: FastMCP, get_connection: "Callable[[], IsaacConnection]") -> None:

    @mcp.tool("play_simulation")
    def play_simulation() -> str:
        """Start the physics simulation."""
        try:
            conn = get_connection()
            result = conn.send_command("simulation.play")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("pause_simulation")
    def pause_simulation() -> str:
        """Pause the physics simulation."""
        try:
            conn = get_connection()
            result = conn.send_command("simulation.pause")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("stop_simulation")
    def stop_simulation() -> str:
        """Stop the physics simulation."""
        try:
            conn = get_connection()
            result = conn.send_command("simulation.stop")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("step_simulation")
    def step_simulation(num_steps: int = 1) -> str:
        """Step the simulation forward by N frames.

        Args:
            num_steps: Number of simulation frames to step.
        """
        try:
            conn = get_connection()
            result = conn.send_command("simulation.step", {"num_steps": num_steps})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("set_physics_params")
    def set_physics_params(gravity: Optional[List[float]] = None, time_step: Optional[float] = None,
                           gpu_enabled: Optional[bool] = None) -> str:
        """Configure physics engine parameters.

        Args:
            gravity: Gravity vector [x, y, z].
            time_step: Physics time step in seconds.
            gpu_enabled: Enable GPU-accelerated physics.
        """
        try:
            conn = get_connection()
            params = {}
            if gravity is not None: params["gravity"] = gravity
            if time_step is not None: params["time_step"] = time_step
            if gpu_enabled is not None: params["gpu_enabled"] = gpu_enabled
            result = conn.send_command("simulation.set_physics", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_isaac_logs")
    def get_isaac_logs(clear: bool = True, count: int = 100) -> str:
        """Get recent warning and error log messages from the Isaac Sim console.
        Use this to diagnose simulation errors, physics warnings, and script failures.

        Args:
            clear: Clear the log buffer after reading. Default True.
            count: Maximum number of log entries to return.
        """
        try:
            conn = get_connection()
            result = conn.send_command("simulation.get_logs", {"clear": clear, "count": count})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_simulation_state")
    def get_simulation_state() -> str:
        """Get the current simulation state including timeline status, simulation time, and physics dt."""
        try:
            conn = get_connection()
            result = conn.send_command("simulation.get_state")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("execute_script")
    def execute_script(code: str, cwd: Optional[str] = None) -> str:
        """Execute arbitrary Python code in Isaac Sim. Use as an escape hatch for operations not covered by other tools.
        Always verify connection with get_scene_info before executing. Print the code in chat before running for review.

        Args:
            code: Python code to execute in the Isaac Sim context.
            cwd: Optional working directory to add to sys.path before execution.
        """
        try:
            conn = get_connection()
            params = {"code": code}
            if cwd is not None:
                params["cwd"] = cwd
            result = conn.send_command("simulation.execute_script", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
