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

"""Scene management command handlers."""
from __future__ import annotations

import traceback
from typing import Any, Dict, Optional, Sequence

from ..adapters.base import IsaacAdapterBase


_discovered_envs: Optional[Dict[str, Dict[str, str]]] = None


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["scene.get_info"] = lambda **p: get_info(adapter, **p)
    registry["scene.create_physics"] = lambda **p: create_physics(adapter, **p)
    registry["scene.clear"] = lambda **p: clear(adapter, **p)
    registry["scene.list_prims"] = lambda **p: list_prims(adapter, **p)
    registry["scene.get_prim_info"] = lambda **p: get_prim_info(adapter, **p)
    registry["scene.list_environments"] = lambda **p: list_environments(adapter, **p)
    registry["scene.load_environment"] = lambda **p: load_environment(adapter, **p)


def get_info(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    try:
        stage = adapter.get_stage()
        assets_root = adapter.get_assets_root_path()
        prim_count = len(list(stage.TraverseAll()))
        stage_path = stage.GetRootLayer().realPath
        return {
            "status": "success",
            "message": "pong",
            "assets_root_path": assets_root,
            "stage_path": stage_path,
            "prim_count": prim_count,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_physics(adapter: IsaacAdapterBase, gravity: Optional[Sequence[float]] = None, scene_name: str = "PhysicsScene") -> Dict[str, Any]:
    try:
        scene_path = adapter.create_physics_scene(gravity=gravity, scene_name=scene_name)
        # Create ground plane
        floor_path = "/World/groundPlane"
        adapter.create_prim(floor_path, "Plane")
        return {"status": "success", "message": f"Physics scene created at {scene_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clear(adapter: IsaacAdapterBase, keep_physics: bool = False) -> Dict[str, Any]:
    try:
        stage = adapter.get_stage()
        # Prims to never delete (system prims)
        keep_paths = {"/OmniverseKit_Persp", "/OmniverseKit_Front", "/OmniverseKit_Top",
                      "/OmniverseKit_Right", "/Render", "/Environment"}
        # Clear all root-level prims (robots created at root, etc.)
        root_prim = stage.GetPseudoRoot()
        for child in root_prim.GetChildren():
            path = str(child.GetPath())
            if path in keep_paths:
                continue
            if keep_physics and "Physics" in path:
                continue
            adapter.delete_prim(path)
        return {"status": "success", "message": "Scene cleared"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_prims(adapter: IsaacAdapterBase, root_path: str = "/", prim_type: Optional[str] = None) -> Dict[str, Any]:
    try:
        prims = adapter.list_prims(root_path=root_path, prim_type=prim_type)
        return {"status": "success", "prims": prims}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_prim_info(adapter: IsaacAdapterBase, prim_path: str = "/") -> Dict[str, Any]:
    try:
        info = adapter.get_prim_info(prim_path)
        return {"status": "success", **info}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _get_env_library(adapter: IsaacAdapterBase) -> Dict[str, Dict[str, str]]:
    global _discovered_envs
    if _discovered_envs is not None:
        return _discovered_envs
    try:
        envs = adapter.discover_environments()
        if envs:
            _discovered_envs = envs
            print(f"Discovered {len(envs)} environments from asset server")
            return _discovered_envs
    except Exception as e:
        print(f"Environment discovery failed: {e}")
    _discovered_envs = {}
    return _discovered_envs


def list_environments(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    library = _get_env_library(adapter)
    return {"status": "success", "environment_count": len(library), "environments": library}


def load_environment(adapter: IsaacAdapterBase, environment: Optional[str] = None, prim_path: str = "/Environment") -> Dict[str, Any]:
    try:
        if not environment:
            return {"status": "error", "message": "environment is required. Use scene.list_environments to see options."}

        library = _get_env_library(adapter)
        q = environment.lower().strip()

        # Exact match
        match = library.get(q)

        # Fuzzy match
        if not match:
            for key, info in library.items():
                if q in key or q in info.get("description", "").lower():
                    match = info
                    break

        if not match:
            available = list(library.keys())[:15]
            return {"status": "error", "message": f"Environment '{environment}' not found. Options: {available}"}

        assets_root = adapter.get_assets_root_path()
        full_path = assets_root + match["asset_path"]
        adapter.load_environment(full_path, prim_path)
        return {"status": "success", "message": f"Loaded environment: {match['description']}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}
