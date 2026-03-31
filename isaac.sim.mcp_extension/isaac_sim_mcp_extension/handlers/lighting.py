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

"""Lighting command handlers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from ..adapters.base import IsaacAdapterBase


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["lighting.create"] = lambda **p: create(adapter, **p)
    registry["lighting.modify"] = lambda **p: modify(adapter, **p)


def create(adapter: IsaacAdapterBase, light_type: str = "DistantLight", position: Optional[Sequence[float]] = None, intensity: float = 1000.0, color: Optional[Sequence[float]] = None, rotation: Optional[Sequence[float]] = None, prim_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            stage = adapter.get_stage()
            count = len(list(stage.TraverseAll()))
            prim_path = f"/World/{light_type}_{count}"
        adapter.create_light(light_type, prim_path, intensity=intensity, color=color, position=position, rotation=rotation)
        return {"status": "success", "message": f"Created {light_type}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def modify(adapter: IsaacAdapterBase, prim_path: Optional[str] = None, intensity: Optional[float] = None, color: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.modify_light(prim_path, intensity=intensity, color=color)
        return {"status": "success", "message": f"Modified light at {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
