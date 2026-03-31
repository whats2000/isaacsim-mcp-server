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

"""Abstract base adapter for Isaac Sim version-specific APIs."""

from __future__ import annotations

import numpy as np
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from pxr import Usd


class IsaacAdapterBase(ABC):
    """Abstract interface that isolates all Isaac Sim version-specific API calls.

    Handler code should never import isaacsim.* directly — use this adapter instead.
    Each supported Isaac Sim version provides a concrete implementation.
    """

    # ── Scene ──────────────────────────────────────────────

    @abstractmethod
    def get_stage(self) -> Usd.Stage:
        """Return the current USD stage."""
        ...

    @abstractmethod
    def get_assets_root_path(self) -> str:
        """Return the root path for Isaac Sim built-in assets."""
        ...

    @abstractmethod
    def discover_environments(self) -> Dict[str, Dict[str, str]]:
        """Scan the asset server for available environment USD files."""
        ...

    @abstractmethod
    def load_environment(self, env_path: str, prim_path: str = "/Environment") -> None:
        """Load an environment USD into the stage."""
        ...

    # ── Prims ──────────────────────────────────────────────

    @abstractmethod
    def create_prim(self, prim_path: str, prim_type: str = "Xform", **kwargs) -> Usd.Prim:
        """Create a USD prim at the given path."""
        ...

    @abstractmethod
    def delete_prim(self, prim_path: str) -> bool:
        """Delete a prim from the stage. Returns True on success."""
        ...

    @abstractmethod
    def add_reference_to_stage(self, usd_path: str, prim_path: str) -> Usd.Prim:
        """Add a USD reference to the stage at prim_path."""
        ...

    @abstractmethod
    def set_prim_transform(
        self,
        prim_path: str,
        position: Optional[Sequence[float]] = None,
        rotation: Optional[Sequence[float]] = None,
        scale: Optional[Sequence[float]] = None,
    ) -> None:
        """Set position, rotation, and/or scale on a prim."""
        ...

    @abstractmethod
    def get_prim_transform(self, prim_path: str) -> Dict[str, Any]:
        """Return position, rotation, scale of a prim."""
        ...

    @abstractmethod
    def list_prims(self, root_path: str = "/", prim_type: Optional[str] = None) -> List[Dict[str, str]]:
        """List prims under root_path, optionally filtered by type."""
        ...

    @abstractmethod
    def get_prim_info(self, prim_path: str) -> Dict[str, Any]:
        """Return detailed info about a prim (type, transform, properties)."""
        ...

    # ── Robots ─────────────────────────────────────────────

    @abstractmethod
    def create_xform_prim(self, prim_path: str) -> Any:
        """Create an XFormPrim wrapper for positioning."""
        ...

    @abstractmethod
    def create_articulation(self, prim_path: str, name: str) -> Any:
        """Create an Articulation wrapper for a robot at prim_path."""
        ...

    @abstractmethod
    def discover_robots(self) -> Dict[str, Dict[str, str]]:
        """Scan the asset server for available robot USD files.

        Returns a dict mapping robot key to {"asset_path": ..., "description": ..., "manufacturer": ...}.
        """
        ...

    @abstractmethod
    def get_robot_joint_info(self, prim_path: str) -> Dict[str, Any]:
        """Return joint names, DOF count, and current positions for a robot."""
        ...

    @abstractmethod
    def set_joint_positions(
        self, prim_path: str, positions: Sequence[float], joint_indices: Optional[List[int]] = None
    ) -> None:
        """Set target joint positions on a robot articulation."""
        ...

    @abstractmethod
    def get_joint_positions(self, prim_path: str) -> List[float]:
        """Read current joint positions from a robot articulation."""
        ...

    # ── Physics ────────────────────────────────────────────

    @abstractmethod
    def create_world(self, **kwargs) -> Any:
        """Create a World instance for simulation management."""
        ...

    @abstractmethod
    def create_simulation_context(self, **kwargs) -> Any:
        """Create a SimulationContext for physics stepping."""
        ...

    @abstractmethod
    def create_physics_scene(self, gravity: Optional[Sequence[float]] = None, scene_name: str = "PhysicsScene") -> str:
        """Create a physics scene prim with gravity settings."""
        ...

    # ── Sensors ────────────────────────────────────────────

    @abstractmethod
    def create_camera(self, prim_path: str, resolution: Tuple[int, int] = (1280, 720), **kwargs) -> Any:
        """Create a camera sensor at prim_path."""
        ...

    @abstractmethod
    def capture_camera_image(self, prim_path: str) -> np.ndarray:
        """Capture an RGB image from a camera. Returns image data."""
        ...

    @abstractmethod
    def create_lidar(self, prim_path: str, config: Optional[str] = None, **kwargs) -> Any:
        """Create a lidar sensor at prim_path."""
        ...

    @abstractmethod
    def get_lidar_point_cloud(self, prim_path: str) -> np.ndarray:
        """Get point cloud data from a lidar sensor."""
        ...

    # ── Materials ──────────────────────────────────────────

    @abstractmethod
    def create_pbr_material(
        self,
        prim_path: str,
        color: Optional[Sequence[float]] = None,
        roughness: float = 0.5,
        metallic: float = 0.0,
    ) -> Any:
        """Create an OmniPBR material."""
        ...

    @abstractmethod
    def create_physics_material(
        self,
        prim_path: str,
        static_friction: float = 0.5,
        dynamic_friction: float = 0.5,
        restitution: float = 0.0,
    ) -> Any:
        """Create a physics material with friction/restitution."""
        ...

    @abstractmethod
    def apply_material(self, material_path: str, target_prim_path: str) -> None:
        """Bind a material to a prim."""
        ...

    # ── Lighting ───────────────────────────────────────────

    @abstractmethod
    def create_light(
        self,
        light_type: str,
        prim_path: str,
        intensity: float = 1000.0,
        color: Optional[Sequence[float]] = None,
        **kwargs,
    ) -> Any:
        """Create a light prim (Distant, Dome, Sphere, Rect, Disk, Cylinder)."""
        ...

    @abstractmethod
    def modify_light(self, prim_path: str, intensity: Optional[float] = None, color: Optional[Sequence[float]] = None) -> None:
        """Modify properties of an existing light."""
        ...

    @abstractmethod
    def clone_prim(self, source_path: str, target_path: str) -> None:
        """Copy a prim from source_path to target_path."""
        ...

    # ── Assets ─────────────────────────────────────────────

    @abstractmethod
    def import_urdf(self, urdf_path: str, prim_path: str = "/World/robot", **kwargs) -> Any:
        """Import a robot from a URDF file."""
        ...

    # ── Simulation ─────────────────────────────────────────

    @abstractmethod
    def play(self) -> None:
        """Start the simulation."""
        ...

    @abstractmethod
    def pause(self) -> None:
        """Pause the simulation."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the simulation."""
        ...

    @abstractmethod
    def step(self, num_steps: int = 1) -> None:
        """Step the simulation forward."""
        ...

    @abstractmethod
    def execute_script(self, code: str) -> Dict[str, Any]:
        """Execute arbitrary Python code in the Isaac Sim context."""
        ...
