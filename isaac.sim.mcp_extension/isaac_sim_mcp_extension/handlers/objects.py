"""Object creation and manipulation command handlers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from ..adapters.base import IsaacAdapterBase


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["objects.create"] = lambda **p: create(adapter, **p)
    registry["objects.delete"] = lambda **p: delete(adapter, **p)
    registry["objects.transform"] = lambda **p: transform(adapter, **p)
    registry["objects.clone"] = lambda **p: clone(adapter, **p)


def create(adapter: IsaacAdapterBase, object_type: str = "Cube", position: Optional[Sequence[float]] = None, rotation: Optional[Sequence[float]] = None, scale: Optional[Sequence[float]] = None, color: Optional[Sequence[float]] = None, physics_enabled: bool = False, prim_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            stage = adapter.get_stage()
            count = len(list(stage.TraverseAll()))
            prim_path = f"/World/{object_type}_{count}"
        prim = adapter.create_prim(prim_path, prim_type=object_type)
        if position or rotation or scale:
            adapter.set_prim_transform(prim_path, position=position, rotation=rotation, scale=scale)
        return {"status": "success", "message": f"Created {object_type}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def delete(adapter: IsaacAdapterBase, prim_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.delete_prim(prim_path)
        return {"status": "success", "message": f"Deleted {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def transform(adapter: IsaacAdapterBase, prim_path: Optional[str] = None, position: Optional[Sequence[float]] = None, rotation: Optional[Sequence[float]] = None, scale: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.set_prim_transform(prim_path, position=position, rotation=rotation, scale=scale)
        return {"status": "success", "message": f"Transformed {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clone(adapter: IsaacAdapterBase, source_path: Optional[str] = None, target_path: Optional[str] = None, position: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    try:
        if not source_path or not target_path:
            return {"status": "error", "message": "source_path and target_path are required"}
        adapter.clone_prim(source_path, target_path)
        if position:
            adapter.set_prim_transform(target_path, position=position)
        return {"status": "success", "message": f"Cloned {source_path} to {target_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
