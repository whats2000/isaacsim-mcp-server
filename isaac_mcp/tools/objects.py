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

"""Object creation and manipulation MCP tools."""

import json
from typing import TYPE_CHECKING, Callable, List, Optional

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from isaac_mcp.connection import IsaacConnection


def register_tools(mcp: FastMCP, get_connection: "Callable[[], IsaacConnection]") -> None:

    @mcp.tool("create_object")
    def create_object(
        object_type: str = "Cube",
        position: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
        color: Optional[List[float]] = None,
        physics_enabled: bool = False,
        prim_path: Optional[str] = None,
    ) -> str:
        """Create a primitive object in the scene.

        Args:
            object_type: Type of primitive — Cube, Sphere, Cylinder, Cone, Capsule, or Plane.
            position: [x, y, z] world position.
            rotation: [rx, ry, rz] rotation in degrees.
            scale: [sx, sy, sz] scale factors.
            color: [r, g, b] color values (0-1).
            physics_enabled: Enable physics on this object.
            prim_path: Custom prim path. Auto-generated if not provided.
        """
        try:
            conn = get_connection()
            params = {"object_type": object_type, "physics_enabled": physics_enabled}
            if position:
                params["position"] = position
            if rotation:
                params["rotation"] = rotation
            if scale:
                params["scale"] = scale
            if color:
                params["color"] = color
            if prim_path:
                params["prim_path"] = prim_path
            result = conn.send_command("objects.create", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("delete_object")
    def delete_object(prim_path: str) -> str:
        """Delete an object from the scene.

        Args:
            prim_path: The prim path of the object to delete.
        """
        try:
            conn = get_connection()
            result = conn.send_command("objects.delete", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("transform_object")
    def transform_object(
        prim_path: str,
        position: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
    ) -> str:
        """Set the transform (position, rotation, scale) of an existing object.

        Args:
            prim_path: The prim path of the object to transform.
            position: [x, y, z] new world position.
            rotation: [rx, ry, rz] new rotation in degrees.
            scale: [sx, sy, sz] new scale factors.
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path}
            if position:
                params["position"] = position
            if rotation:
                params["rotation"] = rotation
            if scale:
                params["scale"] = scale
            result = conn.send_command("objects.transform", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("clone_object")
    def clone_object(source_path: str, target_path: str, position: Optional[List[float]] = None) -> str:
        """Duplicate an existing object to a new prim path.

        Args:
            source_path: Prim path of the object to clone.
            target_path: Prim path for the cloned object.
            position: [x, y, z] position for the clone. Keeps original position if not set.
        """
        try:
            conn = get_connection()
            params = {"source_path": source_path, "target_path": target_path}
            if position:
                params["position"] = position
            result = conn.send_command("objects.clone", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
