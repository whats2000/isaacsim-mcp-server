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

"""Robot creation and control command handlers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from ..adapters.base import IsaacAdapterBase


# Hardcoded fallback — used only if live discovery fails.
# Keys are lowercase robot names, asset_path is relative to the assets root.
FALLBACK_ROBOT_LIBRARY: Dict[str, Dict[str, str]] = {
    "frankapanda": {"asset_path": "/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd", "description": "FrankaRobotics FrankaPanda", "manufacturer": "FrankaRobotics"},
    "jetbot": {"asset_path": "/Isaac/Robots/NVIDIA/Jetbot/jetbot.usd", "description": "NVIDIA Jetbot", "manufacturer": "NVIDIA"},
    "carter_v1": {"asset_path": "/Isaac/Robots/NVIDIA/Carter/carter_v1.usd", "description": "NVIDIA Carter", "manufacturer": "NVIDIA"},
    "novacarter": {"asset_path": "/Isaac/Robots/NVIDIA/NovaCarter/nova_carter.usd", "description": "NVIDIA NovaCarter", "manufacturer": "NVIDIA"},
    "g1": {"asset_path": "/Isaac/Robots/Unitree/G1/g1.usd", "description": "Unitree G1", "manufacturer": "Unitree"},
    "go1": {"asset_path": "/Isaac/Robots/Unitree/Go1/go1.usd", "description": "Unitree Go1", "manufacturer": "Unitree"},
    "spot": {"asset_path": "/Isaac/Robots/BostonDynamics/spot/spot.usd", "description": "BostonDynamics spot", "manufacturer": "BostonDynamics"},
}

# Cached discovered robots — populated on first call to list_robots.
_discovered_robots: Optional[Dict[str, Dict[str, str]]] = None


def _get_robot_library(adapter: IsaacAdapterBase) -> Dict[str, Dict[str, str]]:
    """Return the robot library, discovering from the asset server on first call.

    Falls back to FALLBACK_ROBOT_LIBRARY if discovery fails.
    """
    global _discovered_robots
    if _discovered_robots is not None:
        return _discovered_robots

    try:
        robots = adapter.discover_robots()
        if robots:
            _discovered_robots = robots
            print(f"Discovered {len(robots)} robots from asset server")
            return _discovered_robots
    except Exception as e:
        print(f"Robot discovery failed, using fallback: {e}")

    _discovered_robots = FALLBACK_ROBOT_LIBRARY
    return _discovered_robots


def _find_robot(adapter: IsaacAdapterBase, query: str) -> Optional[Dict[str, Any]]:
    """Find a robot by name. Tries exact key match, then partial match on key/description/manufacturer."""
    library = _get_robot_library(adapter)
    q = query.lower().strip()

    # Exact key match
    if q in library:
        return {"key": q, **library[q]}

    # Partial match on key, description, manufacturer
    matches = []
    for key, info in library.items():
        searchable = f"{key} {info.get('description', '')} {info.get('manufacturer', '')}".lower()
        if q in searchable:
            matches.append({"key": key, **info})

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Return closest match (shortest key that contains the query)
        matches.sort(key=lambda m: len(m["key"]))
        return matches[0]

    return None


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["robots.create"] = lambda **p: create(adapter, **p)
    registry["robots.list"] = lambda **p: list_robots(adapter, **p)
    registry["robots.refresh"] = lambda **p: refresh_robots(adapter, **p)
    registry["robots.get_info"] = lambda **p: get_info(adapter, **p)
    registry["robots.set_joints"] = lambda **p: set_joints(adapter, **p)
    registry["robots.get_joints"] = lambda **p: get_joints(adapter, **p)


def create(adapter: IsaacAdapterBase, robot_type: str = "franka", position: Optional[Sequence[float]] = None, name: Optional[str] = None) -> Dict[str, Any]:
    try:
        match = _find_robot(adapter, robot_type)
        if not match:
            library = _get_robot_library(adapter)
            available = list(library.keys())[:20]
            return {"status": "error", "message": f"Robot '{robot_type}' not found. Try robots.list to see available robots. Some options: {available}"}

        assets_root = adapter.get_assets_root_path()
        asset_path = assets_root + match["asset_path"]
        prim_name = name or match["key"].capitalize()
        prim_path = f"/{prim_name}"
        adapter.add_reference_to_stage(asset_path, prim_path)
        if position:
            xform = adapter.create_xform_prim(prim_path)
            xform.set_world_pose(position=np.array(position))
        return {"status": "success", "message": f"Created {match['description']} robot", "prim_path": prim_path, "robot_key": match["key"]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_robots(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    library = _get_robot_library(adapter)
    return {"status": "success", "robot_count": len(library), "robots": library}


def refresh_robots(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    """Force re-scan the asset server for available robots."""
    global _discovered_robots
    _discovered_robots = None
    library = _get_robot_library(adapter)
    return {"status": "success", "message": f"Refreshed robot library, found {len(library)} robots", "robot_count": len(library)}


def get_info(adapter: IsaacAdapterBase, prim_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        info = adapter.get_robot_joint_info(prim_path)
        return {"status": "success", **info}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_joints(adapter: IsaacAdapterBase, prim_path: Optional[str] = None, joint_positions: Optional[Sequence[float]] = None, joint_indices: Optional[List[int]] = None) -> Dict[str, Any]:
    try:
        if not prim_path or joint_positions is None:
            return {"status": "error", "message": "prim_path and joint_positions are required"}
        adapter.set_joint_positions(prim_path, joint_positions, joint_indices)
        return {"status": "success", "message": f"Set joint positions on {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_joints(adapter: IsaacAdapterBase, prim_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        positions = adapter.get_joint_positions(prim_path)
        return {"status": "success", "joint_positions": positions}
    except Exception as e:
        return {"status": "error", "message": str(e)}
