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

"""Scene management MCP tools."""

import json
from typing import TYPE_CHECKING, Callable, List, Optional

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from isaac_mcp.connection import IsaacConnection


def register_tools(mcp: FastMCP, get_connection: "Callable[[], IsaacConnection]") -> None:

    @mcp.tool("get_scene_info")
    def get_scene_info() -> str:
        """Ping the Isaac Sim extension server and return scene information including stage path, assets root, and prim count."""
        try:
            conn = get_connection()
            result = conn.send_command("scene.get_info")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("create_physics_scene")
    def create_physics_scene(gravity: Optional[List[float]] = None, scene_name: str = "PhysicsScene") -> str:
        """Create a physics scene with ground plane. Call get_scene_info first to verify connection.

        Args:
            gravity: Gravity vector [x, y, z]. Default is standard gravity.
            scene_name: Name for the physics scene prim.
        """
        try:
            conn = get_connection()
            params = {"scene_name": scene_name}
            if gravity is not None:
                params["gravity"] = gravity
            result = conn.send_command("scene.create_physics", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("clear_scene")
    def clear_scene(keep_physics: bool = False) -> str:
        """Remove all prims from the scene.

        Args:
            keep_physics: If True, keep physics scene prims.
        """
        try:
            conn = get_connection()
            result = conn.send_command("scene.clear", {"keep_physics": keep_physics})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("list_prims")
    def list_prims(root_path: str = "/", prim_type: Optional[str] = None) -> str:
        """List all prims in the scene, optionally filtered by type.

        Args:
            root_path: Root path to start listing from.
            prim_type: Filter by prim type (e.g. "Mesh", "Xform").
        """
        try:
            conn = get_connection()
            params = {"root_path": root_path}
            if prim_type:
                params["prim_type"] = prim_type
            result = conn.send_command("scene.list_prims", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_prim_info")
    def get_prim_info(prim_path: str) -> str:
        """Get detailed information about a specific prim including type, transform, and children.

        Args:
            prim_path: The USD prim path to inspect.
        """
        try:
            conn = get_connection()
            result = conn.send_command("scene.get_prim_info", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("list_environments")
    def list_environments() -> str:
        """List all available environments discovered from the Isaac Sim asset server.
        Includes warehouses, offices, outdoor scenes, and more."""
        try:
            conn = get_connection()
            result = conn.send_command("scene.list_environments")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("load_environment")
    def load_environment(environment: str, prim_path: str = "/Environment") -> str:
        """Load a pre-built environment into the scene. Supports fuzzy matching.
        Call list_environments first to see available options.

        Args:
            environment: Environment name or search term (e.g. "warehouse", "hospital", "office").
            prim_path: Prim path for the loaded environment.
        """
        try:
            conn = get_connection()
            result = conn.send_command("scene.load_environment", {"environment": environment, "prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
