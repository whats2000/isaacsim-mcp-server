"""Robot creation and control MCP tools."""

import json
from typing import Callable, List, Optional, TYPE_CHECKING
from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from isaac_mcp.connection import IsaacConnection


def register_tools(mcp: FastMCP, get_connection: "Callable[[], IsaacConnection]") -> None:

    @mcp.tool("create_robot")
    def create_robot(robot_type: str = "franka", position: Optional[List[float]] = None, name: Optional[str] = None) -> str:
        """Create a robot from the built-in library. Call create_physics_scene first.

        Args:
            robot_type: Robot type — franka, jetbot, carter, g1, or go1.
            position: [x, y, z] world position.
            name: Custom name for the robot prim.
        """
        try:
            conn = get_connection()
            params = {"robot_type": robot_type}
            if position: params["position"] = position
            if name: params["name"] = name
            result = conn.send_command("robots.create", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("list_available_robots")
    def list_available_robots() -> str:
        """List all available built-in robot types with descriptions."""
        try:
            conn = get_connection()
            result = conn.send_command("robots.list")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_robot_info")
    def get_robot_info(prim_path: str) -> str:
        """Get joint names, DOF count, and current positions for a robot.

        Args:
            prim_path: The prim path of the robot.
        """
        try:
            conn = get_connection()
            result = conn.send_command("robots.get_info", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("set_joint_positions")
    def set_joint_positions(prim_path: str, joint_positions: List[float], joint_indices: Optional[List[int]] = None) -> str:
        """Set target joint positions on a robot.

        Args:
            prim_path: The prim path of the robot.
            joint_positions: List of target joint position values.
            joint_indices: Optional list of joint indices to set. Sets all joints if not provided.
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path, "joint_positions": joint_positions}
            if joint_indices: params["joint_indices"] = joint_indices
            result = conn.send_command("robots.set_joints", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_joint_positions")
    def get_joint_positions(prim_path: str) -> str:
        """Read current joint positions from a robot.

        Args:
            prim_path: The prim path of the robot.
        """
        try:
            conn = get_connection()
            result = conn.send_command("robots.get_joints", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
