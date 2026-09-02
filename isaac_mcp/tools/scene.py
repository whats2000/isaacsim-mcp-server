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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

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
        """Create a physics scene, adding a ground plane only if the stage lacks one.
        Call get_scene_info first to verify connection.

        A loaded environment usually brings its own collision floor, and this does
        not add a second one on top of it. The response reports "ground_plane" —
        the floor objects will actually land on — and "ground_plane_created", false
        when the stage already had one. Read the floor's height from that prim
        rather than assuming z=0; an environment's floor is not always at the origin.

        The check recognises a collision-enabled prim of type Plane, which is what
        the shipped environments author. An environment whose floor is a Mesh is
        NOT recognised, so a second plane is added and two collision floors end up
        on the stage — which one wins is the physics engine's decision. When
        "ground_plane_created" is true after loading an environment, verify the
        floor before placing anything on it.

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
    def clear_scene(keep_physics: bool = False, keep_environment: bool = False) -> str:
        """Remove all prims from the scene.

        Also empties any environment loaded by load_environment, which removes
        that environment's collision floor along with it — so a later
        create_physics_scene finds no floor and supplies its own.
        The stage's defaultLight is always kept — a stage with no
        light renders black, which looks like a broken camera.

        Args:
            keep_physics: If True, keep physics scene prims.
            keep_environment: If True, keep the loaded environment. Reloading one
                costs seconds, so pass this when clearing objects between attempts.
        """
        try:
            conn = get_connection()
            result = conn.send_command(
                "scene.clear", {"keep_physics": keep_physics, "keep_environment": keep_environment}
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("list_prims")
    def list_prims(root_path: str = "/", prim_type: Optional[str] = None, recursive: bool = False) -> str:
        """List the prims directly under root_path, optionally filtered by type.

        One level deep by default, so `list_prims("/")` names /World and
        /Environment rather than everything inside them — a robot alone is
        hundreds of prims. The response echoes `recursive` so a shallow answer
        is never mistaken for a complete one.

        Pass recursive=True to walk the whole subtree. That is the one you want
        when checking whether something was really deleted, or when hunting a
        prim nested under a robot: a Camera at /World/Arm/EyeCam does not appear
        in a shallow listing of /World.

        Args:
            root_path: Root path to start listing from.
            prim_type: Filter by prim type (e.g. "Mesh", "Xform"). With
                recursive=True, non-matching prims are still descended into, so
                a Camera under an Xform is found.
            recursive: Walk the entire subtree instead of one level.
        """
        try:
            conn = get_connection()
            params = {"root_path": root_path}
            if prim_type:
                params["prim_type"] = prim_type
            if recursive:
                params["recursive"] = True
            result = conn.send_command("scene.list_prims", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_prim_info")
    def get_prim_info(prim_path: str) -> str:
        """Get detailed information about a specific prim.

        Returns type, children, and a transform block. Position is reported in
        both frames, under explicit names — there is no bare "position":
          position_local — parent-relative, the value transform_object writes.
          position_world — where the prim actually is on the stage. Use this to
                           reason about distances, reach, or contact. For a
                           robot link such as /World/Franka/fr3_hand_tcp the two
                           differ by the robot's own pose.
        position_world_source is "usd" (derived from the authored transform) or
        "physics" (measured, on Newton). On Newton a body that has been
        simulated may carry position_warning saying both values are its spawn
        pose; read it through get_physics_state instead.

        Also returns rotation [rx, ry, rz] in degrees (XYZ order, the same
        convention transform_object accepts) and scale — both local, like
        position_local. For geometric prims (Cube, Sphere, Cylinder, Cone,
        Capsule), also returns actual_size [x, y, z] in meters accounting for
        scale and default primitive dimensions (world-space, like
        position_world).

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
    def load_environment(environment: str, prim_path: Optional[str] = None) -> str:
        """Load a pre-built environment into the scene. Supports fuzzy matching.
        Call list_environments first to see available options.

        Many shipped environments are authored Y-up and/or in centimeters; those
        are rotated and rescaled to match the stage, and the response reports what
        was applied under "corrections". Read prim_path from the response rather
        than assuming it — it defaults to a named child of /Environment.

        "bounds" carries two different heights, so use the right one:
          floor_height  — the surface objects rest on, measured from the
                          environment's collision floor. Place with
                          position=[x, y, floor_height].
          bounds_min_z  — the lowest authored geometry (trim, a recessed drain,
                          a sunk prop). Not a placement height.
        floor_height_source says which was used. When it reads "bounds_min_z" no
        collision floor could be measured and floor_height is a fallback that may
        be below the real surface — floor_height_warning explains it.

        Args:
            environment: Environment name or search term (e.g. "warehouse", "hospital", "office").
            prim_path: Prim path for the loaded environment. Defaults to
                /Environment/<name>, which keeps it separate from the stage's
                default lighting and lets clear_scene remove it.
        """
        try:
            conn = get_connection()
            params: Dict[str, Any] = {"environment": environment}
            if prim_path:
                params["prim_path"] = prim_path
            result = conn.send_command("scene.load_environment", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
