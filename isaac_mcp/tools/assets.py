"""Asset import and loading MCP tools."""

import json
from typing import List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

    @mcp.tool("import_urdf")
    def import_urdf(urdf_path: str, prim_path: str = "/World/robot", position: Optional[List[float]] = None) -> str:
        """Import a robot from a URDF file into the scene.

        Args:
            urdf_path: Path to the URDF file.
            prim_path: Prim path for the imported robot.
            position: [x, y, z] world position.
        """
        try:
            conn = get_connection()
            params = {"urdf_path": urdf_path, "prim_path": prim_path}
            if position: params["position"] = position
            result = conn.send_command("assets.import_urdf", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("load_usd")
    def load_usd(usd_url: str, prim_path: str = "/World/my_usd",
                 position: Optional[List[float]] = None, scale: Optional[List[float]] = None) -> str:
        """Load a USD asset from a URL or file path into the scene.

        Args:
            usd_url: URL or local path to the USD file.
            prim_path: Prim path for the loaded asset.
            position: [x, y, z] world position.
            scale: [sx, sy, sz] scale factors.
        """
        try:
            conn = get_connection()
            params = {"usd_url": usd_url, "prim_path": prim_path}
            if position: params["position"] = position
            if scale: params["scale"] = scale
            result = conn.send_command("assets.load_usd", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("search_usd")
    def search_usd(text_prompt: str, target_path: str = "/World/my_usd",
                   position: Optional[List[float]] = None, scale: Optional[List[float]] = None) -> str:
        """Search the NVIDIA USD asset library by text description, then load the best match.

        Args:
            text_prompt: Text description of the 3D asset to search for.
            target_path: Prim path for the loaded result.
            position: [x, y, z] world position.
            scale: [sx, sy, sz] scale factors.
        """
        try:
            conn = get_connection()
            params = {"text_prompt": text_prompt, "target_path": target_path}
            if position: params["position"] = position
            if scale: params["scale"] = scale
            result = conn.send_command("assets.search_usd", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("generate_3d")
    def generate_3d(text_prompt: Optional[str] = None, image_url: Optional[str] = None,
                    position: Optional[List[float]] = None, scale: Optional[List[float]] = None) -> str:
        """Generate a 3D model from text or image using Beaver3D, then load it into the scene.

        Args:
            text_prompt: Text description for 3D generation.
            image_url: URL of an image for 3D generation.
            position: [x, y, z] world position for the generated model.
            scale: [sx, sy, sz] scale factors.
        """
        try:
            conn = get_connection()
            params = {}
            if text_prompt: params["text_prompt"] = text_prompt
            if image_url: params["image_url"] = image_url
            if position: params["position"] = position
            if scale: params["scale"] = scale
            result = conn.send_command("assets.generate_3d", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
