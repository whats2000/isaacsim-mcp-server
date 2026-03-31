"""Scene management command handlers."""
from __future__ import annotations

import traceback
from typing import Any, Dict, Optional, Sequence

from ..adapters.base import IsaacAdapterBase


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["scene.get_info"] = lambda **p: get_info(adapter, **p)
    registry["scene.create_physics"] = lambda **p: create_physics(adapter, **p)
    registry["scene.clear"] = lambda **p: clear(adapter, **p)
    registry["scene.list_prims"] = lambda **p: list_prims(adapter, **p)
    registry["scene.get_prim_info"] = lambda **p: get_prim_info(adapter, **p)


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
        root = stage.GetPrimAtPath("/World")
        if root.IsValid():
            children = root.GetAllChildren()
            for child in children:
                path = str(child.GetPath())
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
