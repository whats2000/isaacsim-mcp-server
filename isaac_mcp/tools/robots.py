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

"""Robot creation and control MCP tools."""

import json
from typing import TYPE_CHECKING, Callable, List, Optional

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from isaac_mcp.connection import IsaacConnection


def register_tools(mcp: FastMCP, get_connection: "Callable[[], IsaacConnection]") -> None:

    @mcp.tool("create_robot")
    def create_robot(
        robot_type: str = "franka", position: Optional[List[float]] = None, name: Optional[str] = None
    ) -> str:
        """Create a robot in the scene from the Isaac Sim asset library.

        Supports fuzzy matching — e.g. "franka", "spot", "g1", "go1".
        Call list_available_robots first to see all available robots.
        Call create_physics_scene before creating robots.

        Returns prim_path, robot_key, joint_names, and num_dof so you can
        immediately use set_joint_positions without a follow-up get_robot_info call.

        Args:
            robot_type: Robot name or search term. Fuzzy matched against available robots.
            position: [x, y, z] world position.
            name: Custom name for the robot prim.
        """
        try:
            conn = get_connection()
            params = {"robot_type": robot_type}
            if position:
                params["position"] = position
            if name:
                params["name"] = name
            result = conn.send_command("robots.create", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("list_available_robots")
    def list_available_robots() -> str:
        """List all available robots discovered from the Isaac Sim asset server.
        Returns robot keys, descriptions, manufacturers, and asset paths.
        The list is auto-discovered at startup and reflects the actual assets available in your Isaac Sim version."""
        try:
            conn = get_connection()
            result = conn.send_command("robots.list")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("refresh_robot_library")
    def refresh_robot_library() -> str:
        """Force re-scan the asset server for available robots. Use this if new robot assets were added."""
        try:
            conn = get_connection()
            result = conn.send_command("robots.refresh")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_robot_info")
    def get_robot_info(prim_path: str) -> str:
        """Get robot joint information including names, DOF count, joint types, and limits.

        Call this after create_robot to understand the robot's kinematic structure.
        Returns joint names ordered by DOF index, joint types (revolute/prismatic),
        and joint limits (degrees for revolute, meters for prismatic).

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
    def set_joint_positions(
        prim_path: str, joint_positions: List[float], joint_indices: Optional[List[int]] = None
    ) -> str:
        """Set target joint positions on a robot via ArticulationAction.

        Units: radians for revolute joints, meters for prismatic joints (e.g. gripper fingers).
        Use get_robot_info to discover joint names, types, and limits first.
        After calling this, use step_simulation to advance and observe the result —
        do not use play_simulation + sleep.

        Args:
            prim_path: The prim path of the robot.
            joint_positions: List of target joint position values.
            joint_indices: Optional list of joint indices to set. Sets all joints if not provided.
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path, "joint_positions": joint_positions}
            if joint_indices:
                params["joint_indices"] = joint_indices
            result = conn.send_command("robots.set_joints", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_joint_positions")
    def get_joint_positions(prim_path: str) -> str:
        """Read current joint positions from a robot.

        Units: radians for revolute joints, meters for prismatic joints.
        Joint order matches the joint_names from get_robot_info.
        For a combined step-and-read, prefer step_simulation with observe_joints.

        Args:
            prim_path: The prim path of the robot.
        """
        try:
            conn = get_connection()
            result = conn.send_command("robots.get_joints", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
