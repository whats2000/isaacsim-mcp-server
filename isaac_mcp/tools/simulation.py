"""Simulation control MCP tools."""

import json
from typing import List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

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

    @mcp.tool("execute_script")
    def execute_script(code: str) -> str:
        """Execute arbitrary Python code in Isaac Sim. Use as an escape hatch for operations not covered by other tools.
        Always verify connection with get_scene_info before executing. Print the code in chat before running for review.

        Args:
            code: Python code to execute in the Isaac Sim context.
        """
        try:
            conn = get_connection()
            result = conn.send_command("simulation.execute_script", {"code": code})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
