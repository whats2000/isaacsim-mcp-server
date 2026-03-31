"""Sensor MCP tools."""

import json
from typing import Callable, List, Optional, TYPE_CHECKING
from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from isaac_mcp.connection import IsaacConnection


def register_tools(mcp: FastMCP, get_connection: "Callable[[], IsaacConnection]") -> None:

    @mcp.tool("create_camera")
    def create_camera(prim_path: str = "/World/Camera", position: Optional[List[float]] = None,
                      rotation: Optional[List[float]] = None, resolution: Optional[List[int]] = None) -> str:
        """Add a camera sensor to the scene.

        Args:
            prim_path: Prim path for the camera.
            position: [x, y, z] world position.
            rotation: [rx, ry, rz] rotation in degrees.
            resolution: [width, height] image resolution. Default 1280x720.
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path}
            if position: params["position"] = position
            if rotation: params["rotation"] = rotation
            if resolution: params["resolution"] = resolution
            result = conn.send_command("sensors.create_camera", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("capture_image")
    def capture_image(prim_path: str = "/World/Camera", output_path: Optional[str] = None) -> str:
        """Capture an RGB image from a camera sensor.

        Args:
            prim_path: Prim path of the camera.
            output_path: File path to save the image. Returns metadata only if not set.
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path}
            if output_path: params["output_path"] = output_path
            result = conn.send_command("sensors.capture_image", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("create_lidar")
    def create_lidar(prim_path: str = "/World/Lidar", position: Optional[List[float]] = None,
                     rotation: Optional[List[float]] = None, config: Optional[str] = None) -> str:
        """Add a lidar sensor to the scene.

        Args:
            prim_path: Prim path for the lidar.
            position: [x, y, z] world position.
            rotation: [rx, ry, rz] rotation in degrees.
            config: Lidar configuration name (e.g. "Example_Rotary").
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path}
            if position: params["position"] = position
            if rotation: params["rotation"] = rotation
            if config: params["config"] = config
            result = conn.send_command("sensors.create_lidar", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_lidar_point_cloud")
    def get_lidar_point_cloud(prim_path: str = "/World/Lidar") -> str:
        """Get point cloud data from a lidar sensor.

        Args:
            prim_path: Prim path of the lidar sensor.
        """
        try:
            conn = get_connection()
            result = conn.send_command("sensors.get_point_cloud", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
