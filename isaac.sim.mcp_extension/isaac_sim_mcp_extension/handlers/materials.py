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

"""Material creation and binding command handlers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from ..adapters.base import IsaacAdapterBase


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["materials.create"] = lambda **p: create(adapter, **p)
    registry["materials.apply"] = lambda **p: apply_material(adapter, **p)


def create(adapter: IsaacAdapterBase, material_type: str = "pbr", prim_path: Optional[str] = None, color: Optional[Sequence[float]] = None, roughness: float = 0.5, metallic: float = 0.0,
           static_friction: float = 0.5, dynamic_friction: float = 0.5, restitution: float = 0.0) -> Dict[str, Any]:
    try:
        if not prim_path:
            stage = adapter.get_stage()
            count = len(list(stage.TraverseAll()))
            prim_path = f"/World/Material_{count}"
        if material_type == "pbr":
            adapter.create_pbr_material(prim_path, color=color, roughness=roughness, metallic=metallic)
        elif material_type == "physics":
            adapter.create_physics_material(prim_path, static_friction=static_friction,
                                            dynamic_friction=dynamic_friction, restitution=restitution)
        else:
            return {"status": "error", "message": f"Unknown material type: {material_type}. Options: pbr, physics"}
        return {"status": "success", "message": f"Created {material_type} material", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def apply_material(adapter: IsaacAdapterBase, material_path: Optional[str] = None, target_prim_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not material_path or not target_prim_path:
            return {"status": "error", "message": "material_path and target_prim_path are required"}
        adapter.apply_material(material_path, target_prim_path)
        return {"status": "success", "message": f"Applied {material_path} to {target_prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
