"""Lighting MCP tools."""

import json
from typing import Callable, List, Optional, TYPE_CHECKING
from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from isaac_mcp.connection import IsaacConnection


def register_tools(mcp: FastMCP, get_connection: "Callable[[], IsaacConnection]") -> None:

    @mcp.tool("create_light")
    def create_light(
        light_type: str = "DistantLight",
        position: Optional[List[float]] = None,
        intensity: float = 1000.0,
        color: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        prim_path: Optional[str] = None,
    ) -> str:
        """Create a light in the scene.

        Args:
            light_type: Type of light — DistantLight, DomeLight, SphereLight, RectLight, DiskLight, or CylinderLight.
            position: [x, y, z] world position.
            intensity: Light intensity.
            color: [r, g, b] light color (0-1).
            rotation: [rx, ry, rz] rotation in degrees.
            prim_path: Custom prim path. Auto-generated if not provided.
        """
        try:
            conn = get_connection()
            params = {"light_type": light_type, "intensity": intensity}
            if position: params["position"] = position
            if color: params["color"] = color
            if rotation: params["rotation"] = rotation
            if prim_path: params["prim_path"] = prim_path
            result = conn.send_command("lighting.create", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("modify_light")
    def modify_light(prim_path: str, intensity: Optional[float] = None, color: Optional[List[float]] = None) -> str:
        """Modify properties of an existing light.

        Args:
            prim_path: The prim path of the light to modify.
            intensity: New intensity value.
            color: [r, g, b] new light color (0-1).
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path}
            if intensity is not None: params["intensity"] = intensity
            if color: params["color"] = color
            result = conn.send_command("lighting.modify", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
