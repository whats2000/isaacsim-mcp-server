# Modular MCP Tools Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the monolithic Isaac Sim MCP extension into modular tool categories with an adapter layer for version isolation, expanding from 7 to 31 tools.

**Architecture:** Socket-based MCP server sends dot-notation JSON commands (`category.action`) to an Isaac Sim extension. The extension routes commands through a registry to domain-specific handler modules. All Isaac Sim API calls go through a version adapter (currently v5 for Isaac Sim 5.1.0). The MCP server side mirrors the structure with matching tool modules.

**Tech Stack:** Python 3.11, FastMCP, Isaac Sim 5.1.0 (`isaacsim.*`), USD/OpenUSD (`pxr`)

**Spec:** `docs/superpowers/specs/2026-03-31-modular-mcp-tools-design.md`

**Testing note:** The extension handlers run inside Isaac Sim's Kit runtime and cannot be unit-tested from CLI. Tests cover the MCP server side (connection, tool registration, JSON protocol). Extension handlers are validated structurally (imports, signatures) and tested manually in Isaac Sim.

---

## File Map

### New files to create

**Extension side (`isaac.sim.mcp_extension/isaac_sim_mcp_extension/`):**
- `adapters/__init__.py` — `get_adapter()` factory
- `adapters/base.py` — `IsaacAdapterBase` ABC
- `adapters/v5.py` — `IsaacAdapterV5` for Isaac Sim 5.1.0
- `handlers/__init__.py` — `register_all_handlers(registry, adapter)`
- `handlers/scene.py` — scene command handlers
- `handlers/objects.py` — object command handlers
- `handlers/lighting.py` — lighting command handlers
- `handlers/robots.py` — robot command handlers
- `handlers/sensors.py` — sensor command handlers
- `handlers/materials.py` — material command handlers
- `handlers/assets.py` — asset import command handlers
- `handlers/simulation.py` — simulation control command handlers

**MCP server side (`isaac_mcp/`):**
- `connection.py` — `IsaacConnection` class (extracted from server.py)
- `tools/__init__.py` — `register_all_tools(mcp, get_connection)`
- `tools/scene.py` — scene MCP tools
- `tools/objects.py` — object MCP tools
- `tools/lighting.py` — lighting MCP tools
- `tools/robots.py` — robot MCP tools
- `tools/sensors.py` — sensor MCP tools
- `tools/materials.py` — material MCP tools
- `tools/assets.py` — asset MCP tools
- `tools/simulation.py` — simulation MCP tools

**Tests (`tests/`):**
- `tests/__init__.py`
- `tests/test_connection.py`
- `tests/test_tool_registration.py`
- `tests/test_handler_structure.py`

### Files to modify
- `isaac_mcp/server.py` — slim down to entry point
- `isaac.sim.mcp_extension/isaac_sim_mcp_extension/extension.py` — slim down to registry router

### Files unchanged
- `isaac.sim.mcp_extension/isaac_sim_mcp_extension/gen3d.py`
- `isaac.sim.mcp_extension/isaac_sim_mcp_extension/usd.py`
- `isaac.sim.mcp_extension/config/extension.toml`
- `isaac.sim.mcp_extension/examples/*`

---

## Task 1: Create directory structure and package init files

**Files:**
- Create: `isaac_mcp/tools/__init__.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/__init__.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create directories and empty init files**

```bash
mkdir -p isaac_mcp/tools
mkdir -p isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters
mkdir -p isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 2: Create tools/__init__.py with registration function**

Create `isaac_mcp/tools/__init__.py`:

```python
"""MCP tool modules for Isaac Sim."""


def register_all_tools(mcp, get_connection):
    """Register all MCP tools from submodules.

    Args:
        mcp: FastMCP server instance.
        get_connection: Callable that returns an IsaacConnection.
    """
    from . import scene, objects, lighting, robots, sensors, materials, assets, simulation

    for module in [scene, objects, lighting, robots, sensors, materials, assets, simulation]:
        module.register_tools(mcp, get_connection)
```

- [ ] **Step 3: Create handlers/__init__.py with registration function**

Create `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/__init__.py`:

```python
"""Command handler modules for the Isaac Sim extension."""


def register_all_handlers(registry, adapter):
    """Register all command handlers from submodules.

    Args:
        registry: Dict mapping command type strings to handler callables.
        adapter: IsaacAdapterBase instance for version-specific API calls.
    """
    from . import scene, objects, lighting, robots, sensors, materials, assets, simulation

    for module in [scene, objects, lighting, robots, sensors, materials, assets, simulation]:
        module.register(registry, adapter)
```

- [ ] **Step 4: Create adapters/__init__.py with factory function**

Create `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/__init__.py`:

```python
"""Isaac Sim version adapters."""


def get_adapter():
    """Return the appropriate adapter for the current Isaac Sim version.

    Currently only supports Isaac Sim 5.1.0.
    Future versions will detect the runtime version and return the matching adapter.
    """
    from .v5 import IsaacAdapterV5
    return IsaacAdapterV5()
```

- [ ] **Step 5: Commit**

```bash
git add isaac_mcp/tools/__init__.py \
    isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/__init__.py \
    isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/__init__.py \
    tests/__init__.py
git commit -m "feat: create modular directory structure and package init files"
```

---

## Task 2: Create the adapter layer

**Files:**
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/base.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py`
- Create: `tests/test_handler_structure.py`

- [ ] **Step 1: Create the abstract adapter base**

Create `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/base.py`:

```python
"""Abstract base adapter for Isaac Sim version-specific APIs."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class IsaacAdapterBase(ABC):
    """Abstract interface that isolates all Isaac Sim version-specific API calls.

    Handler code should never import isaacsim.* directly — use this adapter instead.
    Each supported Isaac Sim version provides a concrete implementation.
    """

    # ── Scene ──────────────────────────────────────────────

    @abstractmethod
    def get_stage(self) -> Any:
        """Return the current USD stage."""
        ...

    @abstractmethod
    def get_assets_root_path(self) -> str:
        """Return the root path for Isaac Sim built-in assets."""
        ...

    # ── Prims ──────────────────────────────────────────────

    @abstractmethod
    def create_prim(self, prim_path: str, prim_type: str = "Xform", **kwargs) -> Any:
        """Create a USD prim at the given path."""
        ...

    @abstractmethod
    def delete_prim(self, prim_path: str) -> bool:
        """Delete a prim from the stage. Returns True on success."""
        ...

    @abstractmethod
    def add_reference_to_stage(self, usd_path: str, prim_path: str) -> Any:
        """Add a USD reference to the stage at prim_path."""
        ...

    @abstractmethod
    def set_prim_transform(
        self,
        prim_path: str,
        position: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
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
    def get_robot_joint_info(self, prim_path: str) -> Dict[str, Any]:
        """Return joint names, DOF count, and current positions for a robot."""
        ...

    @abstractmethod
    def set_joint_positions(
        self, prim_path: str, positions: List[float], joint_indices: Optional[List[int]] = None
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
    def create_physics_scene(self, gravity: Optional[List[float]] = None, scene_name: str = "PhysicsScene") -> Any:
        """Create a physics scene prim with gravity settings."""
        ...

    # ── Sensors ────────────────────────────────────────────

    @abstractmethod
    def create_camera(self, prim_path: str, resolution: Tuple[int, int] = (1280, 720), **kwargs) -> Any:
        """Create a camera sensor at prim_path."""
        ...

    @abstractmethod
    def capture_camera_image(self, prim_path: str) -> Any:
        """Capture an RGB image from a camera. Returns image data."""
        ...

    @abstractmethod
    def create_lidar(self, prim_path: str, config: Optional[str] = None, **kwargs) -> Any:
        """Create a lidar sensor at prim_path."""
        ...

    @abstractmethod
    def get_lidar_point_cloud(self, prim_path: str) -> Any:
        """Get point cloud data from a lidar sensor."""
        ...

    # ── Materials ──────────────────────────────────────────

    @abstractmethod
    def create_pbr_material(
        self,
        prim_path: str,
        color: Optional[List[float]] = None,
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
        color: Optional[List[float]] = None,
        **kwargs,
    ) -> Any:
        """Create a light prim (Distant, Dome, Sphere, Rect, Disk, Cylinder)."""
        ...

    @abstractmethod
    def modify_light(self, prim_path: str, intensity: Optional[float] = None, color: Optional[List[float]] = None) -> None:
        """Modify properties of an existing light."""
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
```

- [ ] **Step 2: Create the v5 adapter**

Create `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py`:

```python
"""Isaac Sim 5.1.0 adapter implementation."""

import traceback
from typing import Any, Dict, List, Optional, Tuple

from .base import IsaacAdapterBase


class IsaacAdapterV5(IsaacAdapterBase):
    """Adapter for Isaac Sim 5.1.0 (isaacsim.* namespace)."""

    # ── Scene ──────────────────────────────────────────────

    def get_stage(self):
        import omni.usd
        return omni.usd.get_context().get_stage()

    def get_assets_root_path(self) -> str:
        from isaacsim.storage.native import get_assets_root_path
        return get_assets_root_path()

    # ── Prims ──────────────────────────────────────────────

    def create_prim(self, prim_path: str, prim_type: str = "Xform", **kwargs):
        from isaacsim.core.utils.prims import create_prim
        return create_prim(prim_path, prim_type, **kwargs)

    def delete_prim(self, prim_path: str) -> bool:
        import omni.kit.commands
        omni.kit.commands.execute("DeletePrims", paths=[prim_path])
        return True

    def add_reference_to_stage(self, usd_path: str, prim_path: str):
        from isaacsim.core.utils.stage import add_reference_to_stage
        return add_reference_to_stage(usd_path, prim_path)

    def set_prim_transform(self, prim_path, position=None, rotation=None, scale=None):
        from pxr import UsdGeom, Gf
        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
        xformable = UsdGeom.Xformable(prim)
        if position is not None:
            xformable.ClearXformOpOrder()
            xformable.AddTranslateOp().Set(Gf.Vec3d(*position))
        if rotation is not None:
            xformable.AddRotateXYZOp().Set(Gf.Vec3d(*rotation))
        if scale is not None:
            xformable.AddScaleOp().Set(Gf.Vec3d(*scale))

    def get_prim_transform(self, prim_path: str) -> Dict[str, Any]:
        from pxr import UsdGeom, Gf
        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
        xformable = UsdGeom.Xformable(prim)
        local_transform = xformable.GetLocalTransformation()
        translation = local_transform.ExtractTranslation()
        return {
            "position": [translation[0], translation[1], translation[2]],
        }

    def list_prims(self, root_path="/", prim_type=None):
        stage = self.get_stage()
        root = stage.GetPrimAtPath(root_path)
        results = []
        for prim in root.GetAllChildren():
            ptype = prim.GetTypeName()
            if prim_type and ptype != prim_type:
                continue
            results.append({"path": str(prim.GetPath()), "type": ptype})
        return results

    def get_prim_info(self, prim_path: str) -> Dict[str, Any]:
        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
        transform = self.get_prim_transform(prim_path)
        children = [str(c.GetPath()) for c in prim.GetAllChildren()]
        return {
            "path": prim_path,
            "type": prim.GetTypeName(),
            "transform": transform,
            "children": children,
        }

    # ── Robots ─────────────────────────────────────────────

    def create_xform_prim(self, prim_path):
        from isaacsim.core.prims import SingleXFormPrim
        return SingleXFormPrim(prim_path=prim_path)

    def create_articulation(self, prim_path, name):
        from isaacsim.core.prims import SingleArticulation
        return SingleArticulation(prim_path=prim_path, name=name)

    def get_robot_joint_info(self, prim_path: str) -> Dict[str, Any]:
        from isaacsim.core.prims import SingleArticulation
        art = SingleArticulation(prim_path=prim_path)
        return {
            "joint_names": art.dof_names if art.dof_names else [],
            "num_dof": art.num_dof if art.num_dof else 0,
        }

    def set_joint_positions(self, prim_path, positions, joint_indices=None):
        from isaacsim.core.prims import SingleArticulation
        from isaacsim.core.utils.types import ArticulationAction
        import numpy as np
        art = SingleArticulation(prim_path=prim_path)
        action = ArticulationAction(joint_positions=np.array(positions), joint_indices=np.array(joint_indices) if joint_indices else None)
        controller = art.get_articulation_controller()
        controller.apply_action(action)

    def get_joint_positions(self, prim_path: str) -> List[float]:
        from isaacsim.core.prims import SingleArticulation
        art = SingleArticulation(prim_path=prim_path)
        positions = art.get_joint_positions()
        return positions.tolist() if positions is not None else []

    # ── Physics ────────────────────────────────────────────

    def create_world(self, **kwargs):
        from isaacsim.core.api import World
        return World(**kwargs)

    def create_simulation_context(self, **kwargs):
        from isaacsim.core.api import SimulationContext
        return SimulationContext(**kwargs)

    def create_physics_scene(self, gravity=None, scene_name="PhysicsScene"):
        import omni.kit.commands
        scene_path = f"/World/{scene_name}"
        omni.kit.commands.execute("CreatePrim", prim_path=scene_path, prim_type="PhysicsScene")
        return scene_path

    # ── Sensors ────────────────────────────────────────────

    def create_camera(self, prim_path, resolution=(1280, 720), **kwargs):
        from isaacsim.sensors.camera import Camera
        return Camera(prim_path=prim_path, resolution=resolution, **kwargs)

    def capture_camera_image(self, prim_path):
        from isaacsim.sensors.camera import Camera
        cam = Camera(prim_path=prim_path)
        return cam.get_rgba()

    def create_lidar(self, prim_path, config=None, **kwargs):
        from isaacsim.sensors.rtx import LidarRtx
        return LidarRtx(prim_path=prim_path, config=config or "Example_Rotary", **kwargs)

    def get_lidar_point_cloud(self, prim_path):
        from isaacsim.sensors.rtx import LidarRtx
        lidar = LidarRtx(prim_path=prim_path)
        return lidar.get_point_cloud()

    # ── Materials ──────────────────────────────────────────

    def create_pbr_material(self, prim_path, color=None, roughness=0.5, metallic=0.0):
        from pxr import UsdShade, Sdf, Gf
        stage = self.get_stage()
        material = UsdShade.Material.Define(stage, prim_path)
        shader = UsdShade.Shader.Define(stage, f"{prim_path}/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
        if color:
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color[:3]))
        material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput("surface", Sdf.ValueTypeNames.Token))
        return material

    def create_physics_material(self, prim_path, static_friction=0.5, dynamic_friction=0.5, restitution=0.0):
        from pxr import UsdPhysics
        stage = self.get_stage()
        material = UsdPhysics.MaterialAPI.Apply(stage.DefinePrim(prim_path))
        material.CreateStaticFrictionAttr(static_friction)
        material.CreateDynamicFrictionAttr(dynamic_friction)
        material.CreateRestitutionAttr(restitution)
        return material

    def apply_material(self, material_path, target_prim_path):
        from pxr import UsdShade
        stage = self.get_stage()
        material = UsdShade.Material(stage.GetPrimAtPath(material_path))
        target = stage.GetPrimAtPath(target_prim_path)
        UsdShade.MaterialBindingAPI(target).Bind(material)

    # ── Lighting ───────────────────────────────────────────

    def create_light(self, light_type, prim_path, intensity=1000.0, color=None, **kwargs):
        from pxr import UsdLux, Gf
        stage = self.get_stage()
        light_classes = {
            "DistantLight": UsdLux.DistantLight,
            "DomeLight": UsdLux.DomeLight,
            "SphereLight": UsdLux.SphereLight,
            "RectLight": UsdLux.RectLight,
            "DiskLight": UsdLux.DiskLight,
            "CylinderLight": UsdLux.CylinderLight,
        }
        cls = light_classes.get(light_type)
        if not cls:
            raise ValueError(f"Unknown light type: {light_type}. Options: {list(light_classes.keys())}")
        light = cls.Define(stage, prim_path)
        light.CreateIntensityAttr(intensity)
        if color:
            light.CreateColorAttr(Gf.Vec3f(*color[:3]))
        position = kwargs.get("position")
        if position:
            self.set_prim_transform(prim_path, position=position)
        rotation = kwargs.get("rotation")
        if rotation:
            self.set_prim_transform(prim_path, rotation=rotation)
        return light

    def modify_light(self, prim_path, intensity=None, color=None):
        from pxr import UsdLux, Gf
        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Light not found: {prim_path}")
        if intensity is not None:
            prim.GetAttribute("inputs:intensity").Set(intensity)
        if color is not None:
            prim.GetAttribute("inputs:color").Set(Gf.Vec3f(*color[:3]))

    # ── Assets ─────────────────────────────────────────────

    def import_urdf(self, urdf_path, prim_path="/World/robot", **kwargs):
        import omni.kit.commands
        status, import_config = omni.kit.commands.execute("URDFCreateImportConfig")
        omni.kit.commands.execute("URDFParseFile", urdf_path=urdf_path, import_config=import_config)
        result = omni.kit.commands.execute(
            "URDFImportRobot",
            urdf_path=urdf_path,
            import_config=import_config,
            dest_path=prim_path,
        )
        return result

    # ── Simulation ─────────────────────────────────────────

    def play(self):
        import omni.timeline
        omni.timeline.get_timeline_interface().play()

    def pause(self):
        import omni.timeline
        omni.timeline.get_timeline_interface().pause()

    def stop(self):
        import omni.timeline
        omni.timeline.get_timeline_interface().stop()

    def step(self, num_steps=1):
        import omni.kit.app
        for _ in range(num_steps):
            omni.kit.app.get_app().update()

    def execute_script(self, code: str) -> Dict[str, Any]:
        import omni
        import carb
        from pxr import Usd, UsdGeom, Sdf, Gf
        local_ns = {"omni": omni, "carb": carb, "Usd": Usd, "UsdGeom": UsdGeom, "Sdf": Sdf, "Gf": Gf}
        try:
            exec(code, local_ns)
            return {"status": "success", "message": "Script executed successfully"}
        except Exception as e:
            return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
```

- [ ] **Step 3: Write structural test to validate adapter interface**

Create `tests/test_handler_structure.py`:

```python
"""Validate that the adapter and handler structure is correct."""

import ast
import os

EXTENSION_ROOT = os.path.join(
    os.path.dirname(__file__), "..", "isaac.sim.mcp_extension", "isaac_sim_mcp_extension"
)


def _parse_file(path):
    with open(path) as f:
        return ast.parse(f.read())


def test_adapter_base_has_all_abstract_methods():
    """Verify the base adapter defines all required abstract methods."""
    tree = _parse_file(os.path.join(EXTENSION_ROOT, "adapters", "base.py"))
    methods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name != "__init__":
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                    methods.add(node.name)
                elif isinstance(decorator, ast.Attribute) and decorator.attr == "abstractmethod":
                    methods.add(node.name)
    expected = {
        "get_stage", "get_assets_root_path",
        "create_prim", "delete_prim", "add_reference_to_stage",
        "set_prim_transform", "get_prim_transform", "list_prims", "get_prim_info",
        "create_xform_prim", "create_articulation",
        "get_robot_joint_info", "set_joint_positions", "get_joint_positions",
        "create_world", "create_simulation_context", "create_physics_scene",
        "create_camera", "capture_camera_image", "create_lidar", "get_lidar_point_cloud",
        "create_pbr_material", "create_physics_material", "apply_material",
        "create_light", "modify_light",
        "import_urdf",
        "play", "pause", "stop", "step", "execute_script",
    }
    assert methods == expected, f"Missing: {expected - methods}, Extra: {methods - expected}"


def test_v5_adapter_implements_all_methods():
    """Verify v5 adapter implements every abstract method from base."""
    base_tree = _parse_file(os.path.join(EXTENSION_ROOT, "adapters", "base.py"))
    v5_tree = _parse_file(os.path.join(EXTENSION_ROOT, "adapters", "v5.py"))

    base_methods = set()
    for node in ast.walk(base_tree):
        if isinstance(node, ast.FunctionDef) and node.name != "__init__":
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Name) and decorator.id == "abstractmethod") or \
                   (isinstance(decorator, ast.Attribute) and decorator.attr == "abstractmethod"):
                    base_methods.add(node.name)

    v5_methods = set()
    for node in ast.walk(v5_tree):
        if isinstance(node, ast.FunctionDef):
            v5_methods.add(node.name)

    missing = base_methods - v5_methods
    assert not missing, f"v5 adapter missing implementations: {missing}"


def test_all_handler_modules_have_register():
    """Verify every handler module exposes a register(registry, adapter) function."""
    handlers_dir = os.path.join(EXTENSION_ROOT, "handlers")
    handler_files = [
        "scene.py", "objects.py", "lighting.py", "robots.py",
        "sensors.py", "materials.py", "assets.py", "simulation.py",
    ]
    for filename in handler_files:
        filepath = os.path.join(handlers_dir, filename)
        assert os.path.exists(filepath), f"Handler file missing: {filename}"
        tree = _parse_file(filepath)
        func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert "register" in func_names, f"{filename} missing register() function"
```

- [ ] **Step 4: Run the structural test (expect failure — handler files don't exist yet)**

```bash
cd /home/user/Documents/GitHub/isaac-sim-mcp
python -m pytest tests/test_handler_structure.py -v
```

Expected: First two tests PASS (adapter files exist), third test FAIL (handler files not created yet).

- [ ] **Step 5: Commit**

```bash
git add isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/ tests/
git commit -m "feat: add adapter layer with base ABC and v5 implementation"
```

---

## Task 3: Extract connection module from server.py

**Files:**
- Create: `isaac_mcp/connection.py`
- Create: `tests/test_connection.py`
- Read: `isaac_mcp/server.py` (for source code to extract)

- [ ] **Step 1: Write test for IsaacConnection structure**

Create `tests/test_connection.py`:

```python
"""Test the IsaacConnection module structure."""

import ast
import os


def test_connection_module_exists():
    path = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "connection.py")
    assert os.path.exists(path)


def test_connection_has_required_classes_and_functions():
    path = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "connection.py")
    with open(path) as f:
        tree = ast.parse(f.read())
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "IsaacConnection" in class_names
    assert "get_isaac_connection" in func_names
    # Check IsaacConnection has send_command method
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IsaacConnection":
            methods = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
            assert "connect" in methods
            assert "disconnect" in methods
            assert "send_command" in methods
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_connection.py -v
```

Expected: FAIL — `connection.py` does not exist.

- [ ] **Step 3: Create connection.py by extracting from server.py**

Create `isaac_mcp/connection.py` — extract `IsaacConnection` class and `get_isaac_connection()` from the current `server.py`:

```python
"""Socket connection to the Isaac Sim extension server."""

import socket
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("IsaacMCPServer")


@dataclass
class IsaacConnection:
    """Manages a persistent TCP socket connection to the Isaac Sim extension."""

    host: str = "localhost"
    port: int = 8766
    sock: Optional[socket.socket] = field(default=None, repr=False)

    def connect(self) -> bool:
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Isaac at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Isaac: {e}")
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=16384):
        chunks = []
        sock.settimeout(300.0)
        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        if not chunks:
                            raise Exception("Connection closed before receiving any data")
                        break
                    chunks.append(chunk)
                    try:
                        data = b"".join(chunks)
                        json.loads(data.decode("utf-8"))
                        return data
                    except json.JSONDecodeError:
                        continue
                except socket.timeout:
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    raise
        except socket.timeout:
            pass

        if chunks:
            data = b"".join(chunks)
            try:
                json.loads(data.decode("utf-8"))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        raise Exception("No data received")

    def send_command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Isaac")

        command = {"type": command_type, "params": params or {}}
        try:
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            self.sock.settimeout(300.0)
            response_data = self.receive_full_response(self.sock)
            response = json.loads(response_data.decode("utf-8"))

            if response.get("status") == "error":
                raise Exception(response.get("message", "Unknown error from Isaac"))
            return response.get("result", {})
        except socket.timeout:
            self.sock = None
            raise Exception("Timeout waiting for Isaac response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            self.sock = None
            raise Exception(f"Connection to Isaac lost: {e}")
        except json.JSONDecodeError as e:
            self.sock = None
            raise Exception(f"Invalid response from Isaac: {e}")
        except Exception as e:
            self.sock = None
            raise Exception(f"Communication error with Isaac: {e}")


_isaac_connection: Optional[IsaacConnection] = None


def get_isaac_connection() -> IsaacConnection:
    """Get or create a persistent Isaac connection singleton."""
    global _isaac_connection
    if _isaac_connection is not None:
        return _isaac_connection
    _isaac_connection = IsaacConnection(host="localhost", port=8766)
    if not _isaac_connection.connect():
        _isaac_connection = None
        raise Exception("Could not connect to Isaac. Make sure the Isaac addon is running.")
    return _isaac_connection


def reset_isaac_connection():
    """Disconnect and clear the global connection (used during shutdown)."""
    global _isaac_connection
    if _isaac_connection:
        _isaac_connection.disconnect()
        _isaac_connection = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_connection.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add isaac_mcp/connection.py tests/test_connection.py
git commit -m "feat: extract IsaacConnection into dedicated connection module"
```

---

## Task 4: Create all extension-side handler modules

**Files:**
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/scene.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/objects.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/lighting.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/robots.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/sensors.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/materials.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/assets.py`
- Create: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/simulation.py`

Each handler module follows the same pattern: a `register(registry, adapter)` function that maps command types to handler functions. Handler functions receive the adapter and parameters, call adapter methods, and return `{"status": "success", ...}` or `{"status": "error", ...}`.

- [ ] **Step 1: Create handlers/scene.py**

```python
"""Scene management command handlers."""

import traceback


def register(registry, adapter):
    registry["scene.get_info"] = lambda **p: get_info(adapter, **p)
    registry["scene.create_physics"] = lambda **p: create_physics(adapter, **p)
    registry["scene.clear"] = lambda **p: clear(adapter, **p)
    registry["scene.list_prims"] = lambda **p: list_prims(adapter, **p)
    registry["scene.get_prim_info"] = lambda **p: get_prim_info(adapter, **p)


def get_info(adapter):
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


def create_physics(adapter, gravity=None, scene_name="PhysicsScene"):
    try:
        scene_path = adapter.create_physics_scene(gravity=gravity, scene_name=scene_name)
        # Create ground plane
        import omni.kit.commands
        floor_path = "/World/groundPlane"
        omni.kit.commands.execute("CreatePrim", prim_path=floor_path, prim_type="Plane")
        return {"status": "success", "message": f"Physics scene created at {scene_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clear(adapter, keep_physics=False):
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


def list_prims(adapter, root_path="/", prim_type=None):
    try:
        prims = adapter.list_prims(root_path=root_path, prim_type=prim_type)
        return {"status": "success", "prims": prims}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_prim_info(adapter, prim_path="/"):
    try:
        info = adapter.get_prim_info(prim_path)
        return {"status": "success", **info}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 2: Create handlers/objects.py**

```python
"""Object creation and manipulation command handlers."""


def register(registry, adapter):
    registry["objects.create"] = lambda **p: create(adapter, **p)
    registry["objects.delete"] = lambda **p: delete(adapter, **p)
    registry["objects.transform"] = lambda **p: transform(adapter, **p)
    registry["objects.clone"] = lambda **p: clone(adapter, **p)


def create(adapter, object_type="Cube", position=None, rotation=None, scale=None, color=None, physics_enabled=False, prim_path=None):
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


def delete(adapter, prim_path=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.delete_prim(prim_path)
        return {"status": "success", "message": f"Deleted {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def transform(adapter, prim_path=None, position=None, rotation=None, scale=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.set_prim_transform(prim_path, position=position, rotation=rotation, scale=scale)
        return {"status": "success", "message": f"Transformed {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clone(adapter, source_path=None, target_path=None, position=None):
    try:
        if not source_path or not target_path:
            return {"status": "error", "message": "source_path and target_path are required"}
        import omni.kit.commands
        omni.kit.commands.execute("CopyPrim", path_from=source_path, path_to=target_path)
        if position:
            adapter.set_prim_transform(target_path, position=position)
        return {"status": "success", "message": f"Cloned {source_path} to {target_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 3: Create handlers/lighting.py**

```python
"""Lighting command handlers."""


def register(registry, adapter):
    registry["lighting.create"] = lambda **p: create(adapter, **p)
    registry["lighting.modify"] = lambda **p: modify(adapter, **p)


def create(adapter, light_type="DistantLight", position=None, intensity=1000.0, color=None, rotation=None, prim_path=None):
    try:
        if not prim_path:
            stage = adapter.get_stage()
            count = len(list(stage.TraverseAll()))
            prim_path = f"/World/{light_type}_{count}"
        adapter.create_light(light_type, prim_path, intensity=intensity, color=color, position=position, rotation=rotation)
        return {"status": "success", "message": f"Created {light_type}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def modify(adapter, prim_path=None, intensity=None, color=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.modify_light(prim_path, intensity=intensity, color=color)
        return {"status": "success", "message": f"Modified light at {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 4: Create handlers/robots.py**

```python
"""Robot creation and control command handlers."""

import numpy as np


ROBOT_LIBRARY = {
    "franka": {"asset_path": "/Isaac/Robots/Franka/franka_alt_fingers.usd", "description": "Franka Emika Panda manipulator"},
    "jetbot": {"asset_path": "/Isaac/Robots/Jetbot/jetbot.usd", "description": "NVIDIA JetBot mobile robot"},
    "carter": {"asset_path": "/Isaac/Robots/Carter/carter.usd", "description": "Carter delivery robot"},
    "g1": {"asset_path": "/Isaac/Robots/Unitree/G1/g1.usd", "description": "Unitree G1 humanoid robot"},
    "go1": {"asset_path": "/Isaac/Robots/Unitree/Go1/go1.usd", "description": "Unitree Go1 quadruped robot"},
}


def register(registry, adapter):
    registry["robots.create"] = lambda **p: create(adapter, **p)
    registry["robots.list"] = lambda **p: list_robots(adapter, **p)
    registry["robots.get_info"] = lambda **p: get_info(adapter, **p)
    registry["robots.set_joints"] = lambda **p: set_joints(adapter, **p)
    registry["robots.get_joints"] = lambda **p: get_joints(adapter, **p)


def create(adapter, robot_type="franka", position=None, name=None):
    try:
        robot_type_lower = robot_type.lower()
        if robot_type_lower not in ROBOT_LIBRARY:
            return {"status": "error", "message": f"Unknown robot: {robot_type}. Options: {list(ROBOT_LIBRARY.keys())}"}
        assets_root = adapter.get_assets_root_path()
        asset_path = assets_root + ROBOT_LIBRARY[robot_type_lower]["asset_path"]
        prim_name = name or robot_type_lower.capitalize()
        prim_path = f"/{prim_name}"
        adapter.add_reference_to_stage(asset_path, prim_path)
        if position:
            xform = adapter.create_xform_prim(prim_path)
            xform.set_world_pose(position=np.array(position))
        return {"status": "success", "message": f"Created {robot_type} robot", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_robots(adapter):
    return {"status": "success", "robots": ROBOT_LIBRARY}


def get_info(adapter, prim_path=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        info = adapter.get_robot_joint_info(prim_path)
        return {"status": "success", **info}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_joints(adapter, prim_path=None, joint_positions=None, joint_indices=None):
    try:
        if not prim_path or joint_positions is None:
            return {"status": "error", "message": "prim_path and joint_positions are required"}
        adapter.set_joint_positions(prim_path, joint_positions, joint_indices)
        return {"status": "success", "message": f"Set joint positions on {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_joints(adapter, prim_path=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        positions = adapter.get_joint_positions(prim_path)
        return {"status": "success", "joint_positions": positions}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 5: Create handlers/sensors.py**

```python
"""Sensor creation and data capture command handlers."""

import base64
import os


def register(registry, adapter):
    registry["sensors.create_camera"] = lambda **p: create_camera(adapter, **p)
    registry["sensors.capture_image"] = lambda **p: capture_image(adapter, **p)
    registry["sensors.create_lidar"] = lambda **p: create_lidar(adapter, **p)
    registry["sensors.get_point_cloud"] = lambda **p: get_point_cloud(adapter, **p)


def create_camera(adapter, prim_path="/World/Camera", position=None, rotation=None, resolution=None):
    try:
        res = tuple(resolution) if resolution else (1280, 720)
        cam = adapter.create_camera(prim_path, resolution=res)
        if position or rotation:
            adapter.set_prim_transform(prim_path, position=position, rotation=rotation)
        return {"status": "success", "message": f"Camera created at {prim_path}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def capture_image(adapter, prim_path="/World/Camera", output_path=None):
    try:
        image_data = adapter.capture_camera_image(prim_path)
        if output_path:
            import numpy as np
            from PIL import Image
            img = Image.fromarray(image_data)
            img.save(output_path)
            return {"status": "success", "message": f"Image saved to {output_path}", "output_path": output_path}
        return {"status": "success", "message": "Image captured", "shape": list(image_data.shape) if hasattr(image_data, "shape") else None}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_lidar(adapter, prim_path="/World/Lidar", position=None, rotation=None, config=None):
    try:
        adapter.create_lidar(prim_path, config=config)
        if position or rotation:
            adapter.set_prim_transform(prim_path, position=position, rotation=rotation)
        return {"status": "success", "message": f"Lidar created at {prim_path}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_point_cloud(adapter, prim_path="/World/Lidar"):
    try:
        pc = adapter.get_lidar_point_cloud(prim_path)
        point_count = len(pc) if pc is not None else 0
        return {"status": "success", "message": f"Got {point_count} points", "point_count": point_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 6: Create handlers/materials.py**

```python
"""Material creation and binding command handlers."""


def register(registry, adapter):
    registry["materials.create"] = lambda **p: create(adapter, **p)
    registry["materials.apply"] = lambda **p: apply_material(adapter, **p)


def create(adapter, material_type="pbr", prim_path=None, color=None, roughness=0.5, metallic=0.0,
           static_friction=0.5, dynamic_friction=0.5, restitution=0.0):
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


def apply_material(adapter, material_path=None, target_prim_path=None):
    try:
        if not material_path or not target_prim_path:
            return {"status": "error", "message": "material_path and target_prim_path are required"}
        adapter.apply_material(material_path, target_prim_path)
        return {"status": "success", "message": f"Applied {material_path} to {target_prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 7: Create handlers/assets.py**

```python
"""Asset import and loading command handlers."""

from isaac_sim_mcp_extension.gen3d import Beaver3d
from isaac_sim_mcp_extension.usd import USDLoader, USDSearch3d


def register(registry, adapter):
    registry["assets.import_urdf"] = lambda **p: import_urdf(adapter, **p)
    registry["assets.load_usd"] = lambda **p: load_usd(adapter, **p)
    registry["assets.search_usd"] = lambda **p: search_usd(adapter, **p)
    registry["assets.generate_3d"] = lambda **p: generate_3d(adapter, **p)


def import_urdf(adapter, urdf_path=None, prim_path="/World/robot", position=None):
    try:
        if not urdf_path:
            return {"status": "error", "message": "urdf_path is required"}
        result = adapter.import_urdf(urdf_path, prim_path=prim_path)
        if position:
            adapter.set_prim_transform(prim_path, position=position)
        return {"status": "success", "message": f"Imported URDF from {urdf_path}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def load_usd(adapter, usd_url=None, prim_path="/World/my_usd", position=None, scale=None):
    try:
        if not usd_url:
            return {"status": "error", "message": "usd_url is required"}
        loader = USDLoader()
        result_path = loader.load_usd_from_url(url_path=usd_url, target_path=prim_path, location=position, scale=scale)
        return {"status": "success", "message": f"Loaded USD from {usd_url}", "prim_path": result_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_usd(adapter, text_prompt=None, target_path="/World/my_usd", position=None, scale=None):
    try:
        if not text_prompt:
            return {"status": "error", "message": "text_prompt is required"}
        searcher = USDSearch3d()
        url = searcher.search(text_prompt)
        loader = USDLoader()
        prim_path = loader.load_usd_from_url(url_path=url, target_path=target_path)
        return {"status": "success", "message": f"Found and loaded USD for '{text_prompt}'", "prim_path": prim_path, "url": url}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def generate_3d(adapter, text_prompt=None, image_url=None, position=None, scale=None):
    try:
        if not text_prompt and not image_url:
            return {"status": "error", "message": "Either text_prompt or image_url is required"}
        beaver = Beaver3d()
        if image_url:
            task_id = beaver.generate_3d_from_image(image_url)
        else:
            task_id = beaver.generate_3d_from_text(text_prompt)

        def on_complete(task_id, status, result_path):
            loader = USDLoader()
            loader.load_usd_model(task_id=task_id)
            try:
                loader.load_texture_and_create_material(task_id=task_id)
                loader.bind_texture_to_model()
            except Exception:
                pass
            if position or scale:
                loader.transform(position=position or (0, 0, 50), scale=scale or (10, 10, 10))

        from omni.kit.async_engine import run_coroutine
        run_coroutine(beaver.monitor_task_status_async(task_id, on_complete_callback=on_complete))
        return {"status": "success", "message": f"3D generation started", "task_id": task_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 8: Create handlers/simulation.py**

```python
"""Simulation control command handlers."""


def register(registry, adapter):
    registry["simulation.play"] = lambda **p: play(adapter, **p)
    registry["simulation.pause"] = lambda **p: pause(adapter, **p)
    registry["simulation.stop"] = lambda **p: stop(adapter, **p)
    registry["simulation.step"] = lambda **p: step(adapter, **p)
    registry["simulation.set_physics"] = lambda **p: set_physics(adapter, **p)
    registry["simulation.execute_script"] = lambda **p: execute_script(adapter, **p)


def play(adapter):
    try:
        adapter.play()
        return {"status": "success", "message": "Simulation started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def pause(adapter):
    try:
        adapter.pause()
        return {"status": "success", "message": "Simulation paused"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def stop(adapter):
    try:
        adapter.stop()
        return {"status": "success", "message": "Simulation stopped"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def step(adapter, num_steps=1):
    try:
        adapter.step(num_steps=num_steps)
        return {"status": "success", "message": f"Stepped {num_steps} frames"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_physics(adapter, gravity=None, time_step=None, gpu_enabled=None):
    try:
        # Physics params are set via the PhysicsContext on the World
        # For now, gravity is the most common parameter
        if gravity is not None:
            adapter.create_physics_scene(gravity=gravity)
        return {"status": "success", "message": "Physics parameters updated"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def execute_script(adapter, code=None):
    try:
        if not code:
            return {"status": "error", "message": "code is required"}
        result = adapter.execute_script(code)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 9: Run structural test to verify all handlers pass**

```bash
python -m pytest tests/test_handler_structure.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 10: Commit**

```bash
git add isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/
git commit -m "feat: add all 8 handler modules with 31 command handlers"
```

---

## Task 5: Create all MCP server-side tool modules

**Files:**
- Create: `isaac_mcp/tools/scene.py`
- Create: `isaac_mcp/tools/objects.py`
- Create: `isaac_mcp/tools/lighting.py`
- Create: `isaac_mcp/tools/robots.py`
- Create: `isaac_mcp/tools/sensors.py`
- Create: `isaac_mcp/tools/materials.py`
- Create: `isaac_mcp/tools/assets.py`
- Create: `isaac_mcp/tools/simulation.py`
- Create: `tests/test_tool_registration.py`

Each tool module follows the same pattern: a `register_tools(mcp, get_connection)` function that registers MCP tools. Each tool calls `get_connection().send_command("category.action", params)` and returns the result.

- [ ] **Step 1: Write test for tool registration structure**

Create `tests/test_tool_registration.py`:

```python
"""Test that all tool modules have correct structure."""

import ast
import os

TOOLS_DIR = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "tools")

EXPECTED_MODULES = [
    "scene.py", "objects.py", "lighting.py", "robots.py",
    "sensors.py", "materials.py", "assets.py", "simulation.py",
]


def test_all_tool_modules_exist():
    for filename in EXPECTED_MODULES:
        path = os.path.join(TOOLS_DIR, filename)
        assert os.path.exists(path), f"Missing tool module: {filename}"


def test_all_tool_modules_have_register_tools():
    for filename in EXPECTED_MODULES:
        path = os.path.join(TOOLS_DIR, filename)
        with open(path) as f:
            tree = ast.parse(f.read())
        func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert "register_tools" in func_names, f"{filename} missing register_tools() function"


def test_init_imports_all_modules():
    path = os.path.join(TOOLS_DIR, "__init__.py")
    with open(path) as f:
        content = f.read()
    for module_name in ["scene", "objects", "lighting", "robots", "sensors", "materials", "assets", "simulation"]:
        assert module_name in content, f"tools/__init__.py missing import of {module_name}"
```

- [ ] **Step 2: Create tools/scene.py**

```python
"""Scene management MCP tools."""

import json
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

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
        """Create a physics scene with ground plane. Call get_scene_info first to verify connection.

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
    def clear_scene(keep_physics: bool = False) -> str:
        """Remove all prims from the scene.

        Args:
            keep_physics: If True, keep physics scene prims.
        """
        try:
            conn = get_connection()
            result = conn.send_command("scene.clear", {"keep_physics": keep_physics})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("list_prims")
    def list_prims(root_path: str = "/", prim_type: Optional[str] = None) -> str:
        """List all prims in the scene, optionally filtered by type.

        Args:
            root_path: Root path to start listing from.
            prim_type: Filter by prim type (e.g. "Mesh", "Xform").
        """
        try:
            conn = get_connection()
            params = {"root_path": root_path}
            if prim_type:
                params["prim_type"] = prim_type
            result = conn.send_command("scene.list_prims", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_prim_info")
    def get_prim_info(prim_path: str) -> str:
        """Get detailed information about a specific prim including type, transform, and children.

        Args:
            prim_path: The USD prim path to inspect.
        """
        try:
            conn = get_connection()
            result = conn.send_command("scene.get_prim_info", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
```

- [ ] **Step 3: Create tools/objects.py**

```python
"""Object creation and manipulation MCP tools."""

import json
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

    @mcp.tool("create_object")
    def create_object(
        object_type: str = "Cube",
        position: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
        color: Optional[List[float]] = None,
        physics_enabled: bool = False,
        prim_path: Optional[str] = None,
    ) -> str:
        """Create a primitive object in the scene.

        Args:
            object_type: Type of primitive — Cube, Sphere, Cylinder, Cone, Capsule, or Plane.
            position: [x, y, z] world position.
            rotation: [rx, ry, rz] rotation in degrees.
            scale: [sx, sy, sz] scale factors.
            color: [r, g, b] color values (0-1).
            physics_enabled: Enable physics on this object.
            prim_path: Custom prim path. Auto-generated if not provided.
        """
        try:
            conn = get_connection()
            params = {"object_type": object_type, "physics_enabled": physics_enabled}
            if position: params["position"] = position
            if rotation: params["rotation"] = rotation
            if scale: params["scale"] = scale
            if color: params["color"] = color
            if prim_path: params["prim_path"] = prim_path
            result = conn.send_command("objects.create", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("delete_object")
    def delete_object(prim_path: str) -> str:
        """Delete an object from the scene.

        Args:
            prim_path: The prim path of the object to delete.
        """
        try:
            conn = get_connection()
            result = conn.send_command("objects.delete", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("transform_object")
    def transform_object(
        prim_path: str,
        position: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
    ) -> str:
        """Set the transform (position, rotation, scale) of an existing object.

        Args:
            prim_path: The prim path of the object to transform.
            position: [x, y, z] new world position.
            rotation: [rx, ry, rz] new rotation in degrees.
            scale: [sx, sy, sz] new scale factors.
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path}
            if position: params["position"] = position
            if rotation: params["rotation"] = rotation
            if scale: params["scale"] = scale
            result = conn.send_command("objects.transform", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("clone_object")
    def clone_object(source_path: str, target_path: str, position: Optional[List[float]] = None) -> str:
        """Duplicate an existing object to a new prim path.

        Args:
            source_path: Prim path of the object to clone.
            target_path: Prim path for the cloned object.
            position: [x, y, z] position for the clone. Keeps original position if not set.
        """
        try:
            conn = get_connection()
            params = {"source_path": source_path, "target_path": target_path}
            if position: params["position"] = position
            result = conn.send_command("objects.clone", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
```

- [ ] **Step 4: Create tools/lighting.py**

```python
"""Lighting MCP tools."""

import json
from typing import List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

    @mcp.tool("create_light")
    def create_light(
        light_type: str = "DistantLight",
        position: Optional[List[float]] = None,
        intensity: float = 1000.0,
        color: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        prim_path: Optional[str] = None,
    ) -> str:
        """Create a light in the scene.

        Args:
            light_type: Type of light — DistantLight, DomeLight, SphereLight, RectLight, DiskLight, or CylinderLight.
            position: [x, y, z] world position.
            intensity: Light intensity.
            color: [r, g, b] light color (0-1).
            rotation: [rx, ry, rz] rotation in degrees.
            prim_path: Custom prim path. Auto-generated if not provided.
        """
        try:
            conn = get_connection()
            params = {"light_type": light_type, "intensity": intensity}
            if position: params["position"] = position
            if color: params["color"] = color
            if rotation: params["rotation"] = rotation
            if prim_path: params["prim_path"] = prim_path
            result = conn.send_command("lighting.create", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("modify_light")
    def modify_light(prim_path: str, intensity: Optional[float] = None, color: Optional[List[float]] = None) -> str:
        """Modify properties of an existing light.

        Args:
            prim_path: The prim path of the light to modify.
            intensity: New intensity value.
            color: [r, g, b] new light color (0-1).
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path}
            if intensity is not None: params["intensity"] = intensity
            if color: params["color"] = color
            result = conn.send_command("lighting.modify", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
```

- [ ] **Step 5: Create tools/robots.py**

```python
"""Robot creation and control MCP tools."""

import json
from typing import List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

    @mcp.tool("create_robot")
    def create_robot(robot_type: str = "franka", position: Optional[List[float]] = None, name: Optional[str] = None) -> str:
        """Create a robot from the built-in library. Call create_physics_scene first.

        Args:
            robot_type: Robot type — franka, jetbot, carter, g1, or go1.
            position: [x, y, z] world position.
            name: Custom name for the robot prim.
        """
        try:
            conn = get_connection()
            params = {"robot_type": robot_type}
            if position: params["position"] = position
            if name: params["name"] = name
            result = conn.send_command("robots.create", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("list_available_robots")
    def list_available_robots() -> str:
        """List all available built-in robot types with descriptions."""
        try:
            conn = get_connection()
            result = conn.send_command("robots.list")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_robot_info")
    def get_robot_info(prim_path: str) -> str:
        """Get joint names, DOF count, and current positions for a robot.

        Args:
            prim_path: The prim path of the robot.
        """
        try:
            conn = get_connection()
            result = conn.send_command("robots.get_info", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("set_joint_positions")
    def set_joint_positions(prim_path: str, joint_positions: List[float], joint_indices: Optional[List[int]] = None) -> str:
        """Set target joint positions on a robot.

        Args:
            prim_path: The prim path of the robot.
            joint_positions: List of target joint position values.
            joint_indices: Optional list of joint indices to set. Sets all joints if not provided.
        """
        try:
            conn = get_connection()
            params = {"prim_path": prim_path, "joint_positions": joint_positions}
            if joint_indices: params["joint_indices"] = joint_indices
            result = conn.send_command("robots.set_joints", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("get_joint_positions")
    def get_joint_positions(prim_path: str) -> str:
        """Read current joint positions from a robot.

        Args:
            prim_path: The prim path of the robot.
        """
        try:
            conn = get_connection()
            result = conn.send_command("robots.get_joints", {"prim_path": prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
```

- [ ] **Step 6: Create tools/sensors.py**

```python
"""Sensor MCP tools."""

import json
from typing import List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

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
```

- [ ] **Step 7: Create tools/materials.py**

```python
"""Material MCP tools."""

import json
from typing import List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

    @mcp.tool("create_material")
    def create_material(
        material_type: str = "pbr",
        prim_path: Optional[str] = None,
        color: Optional[List[float]] = None,
        roughness: float = 0.5,
        metallic: float = 0.0,
    ) -> str:
        """Create a PBR or physics material.

        Args:
            material_type: "pbr" for visual material or "physics" for physics material.
            prim_path: Prim path for the material. Auto-generated if not set.
            color: [r, g, b] diffuse color (0-1). PBR only.
            roughness: Surface roughness (0-1). PBR only.
            metallic: Metallic value (0-1). PBR only.
        """
        try:
            conn = get_connection()
            params = {"material_type": material_type, "roughness": roughness, "metallic": metallic}
            if prim_path: params["prim_path"] = prim_path
            if color: params["color"] = color
            result = conn.send_command("materials.create", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("apply_material")
    def apply_material(material_path: str, target_prim_path: str) -> str:
        """Bind a material to an object.

        Args:
            material_path: Prim path of the material.
            target_prim_path: Prim path of the object to apply the material to.
        """
        try:
            conn = get_connection()
            result = conn.send_command("materials.apply", {"material_path": material_path, "target_prim_path": target_prim_path})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
```

- [ ] **Step 8: Create tools/assets.py**

```python
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
```

- [ ] **Step 9: Create tools/simulation.py**

```python
"""Simulation control MCP tools."""

import json
from typing import List, Optional
from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP, get_connection):

    @mcp.tool("play_simulation")
    def play_simulation() -> str:
        """Start the physics simulation."""
        try:
            conn = get_connection()
            result = conn.send_command("simulation.play")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("pause_simulation")
    def pause_simulation() -> str:
        """Pause the physics simulation."""
        try:
            conn = get_connection()
            result = conn.send_command("simulation.pause")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("stop_simulation")
    def stop_simulation() -> str:
        """Stop the physics simulation."""
        try:
            conn = get_connection()
            result = conn.send_command("simulation.stop")
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("step_simulation")
    def step_simulation(num_steps: int = 1) -> str:
        """Step the simulation forward by N frames.

        Args:
            num_steps: Number of simulation frames to step.
        """
        try:
            conn = get_connection()
            result = conn.send_command("simulation.step", {"num_steps": num_steps})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("set_physics_params")
    def set_physics_params(gravity: Optional[List[float]] = None, time_step: Optional[float] = None,
                           gpu_enabled: Optional[bool] = None) -> str:
        """Configure physics engine parameters.

        Args:
            gravity: Gravity vector [x, y, z].
            time_step: Physics time step in seconds.
            gpu_enabled: Enable GPU-accelerated physics.
        """
        try:
            conn = get_connection()
            params = {}
            if gravity is not None: params["gravity"] = gravity
            if time_step is not None: params["time_step"] = time_step
            if gpu_enabled is not None: params["gpu_enabled"] = gpu_enabled
            result = conn.send_command("simulation.set_physics", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @mcp.tool("execute_script")
    def execute_script(code: str) -> str:
        """Execute arbitrary Python code in Isaac Sim. Use as an escape hatch for operations not covered by other tools.
        Always verify connection with get_scene_info before executing. Print the code in chat before running for review.

        Args:
            code: Python code to execute in the Isaac Sim context.
        """
        try:
            conn = get_connection()
            result = conn.send_command("simulation.execute_script", {"code": code})
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
```

- [ ] **Step 10: Run tool registration tests**

```bash
python -m pytest tests/test_tool_registration.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 11: Commit**

```bash
git add isaac_mcp/tools/ tests/test_tool_registration.py
git commit -m "feat: add all 8 MCP tool modules with 31 tools"
```

---

## Task 6: Rewrite server.py as slim entry point

**Files:**
- Modify: `isaac_mcp/server.py`

- [ ] **Step 1: Rewrite server.py**

Replace the entire contents of `isaac_mcp/server.py` with:

```python
"""Isaac Sim MCP Server — entry point.

Registers all tools from tools/ submodules and starts the FastMCP server.
"""

import logging
from mcp.server.fastmcp import FastMCP
from isaac_mcp.connection import get_isaac_connection, reset_isaac_connection
from isaac_mcp.tools import register_all_tools
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("IsaacMCPServer")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle."""
    try:
        logger.info("IsaacMCP server starting up")
        try:
            get_isaac_connection()
            logger.info("Successfully connected to Isaac on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Isaac on startup: {e}")
        yield {}
    finally:
        reset_isaac_connection()
        logger.info("IsaacMCP server shut down")


mcp = FastMCP(
    "IsaacSimMCP",
    description="Isaac Sim integration through the Model Context Protocol",
    lifespan=server_lifespan,
)

register_all_tools(mcp, get_isaac_connection)


@mcp.prompt()
def asset_creation_strategy() -> str:
    """Defines the preferred strategy for creating assets in Isaac Sim"""
    return """
    0. Before anything, always check the scene with get_scene_info() to verify connection and get the assets root path.
    1. If the scene is empty, create a physics scene with create_physics_scene().
    2. If execute_script fails due to communication error, retry up to 3 times.
    3. Use create_robot() as the first attempt for robot creation before falling back to execute_script().
    4. Use create_light() to add lighting to the scene.
    5. Use create_object() for primitive shapes, create_material() + apply_material() for appearance.
    6. Use play_simulation() / stop_simulation() to control the simulation lifecycle.
    """


def main():
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the server module can be imported without Isaac Sim**

```bash
python -c "import ast; ast.parse(open('isaac_mcp/server.py').read()); print('server.py parses OK')"
```

Expected: `server.py parses OK`

- [ ] **Step 3: Commit**

```bash
git add isaac_mcp/server.py
git commit -m "refactor: rewrite server.py as slim entry point using modular tools"
```

---

## Task 7: Rewrite extension.py as slim registry router

**Files:**
- Modify: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/extension.py`

- [ ] **Step 1: Rewrite extension.py**

Replace the entire contents of `isaac.sim.mcp_extension/isaac_sim_mcp_extension/extension.py` with:

```python
"""Isaac Sim MCP Extension — slim entry point.

Routes incoming socket commands to handler modules via a registry.
"""

import gc
import json
import socket
import threading
import time
import traceback

import carb
import omni.ext
import omni.usd

from .adapters import get_adapter
from .handlers import register_all_handlers


class MCPExtension(omni.ext.IExt):

    def __init__(self):
        super().__init__()
        self.ext_id = None
        self.running = False
        self.host = None
        self.port = None
        self._socket = None
        self._server_thread = None
        self._settings = carb.settings.get_settings()
        self._registry = {}
        self._adapter = None

    def on_startup(self, ext_id: str):
        print("trigger  on_startup for: ", ext_id)
        self.ext_id = ext_id
        self.port = self._settings.get("/exts/isaac.sim.mcp/server.port") or 8766
        self.host = self._settings.get("/exts/isaac.sim.mcp/server.host") or "localhost"

        # Initialize adapter and register handlers
        self._adapter = get_adapter()
        register_all_handlers(self._registry, self._adapter)
        print(f"Registered {len(self._registry)} command handlers")

        self._start_server()

    def on_shutdown(self):
        print("trigger  on_shutdown for: ", self.ext_id)
        self._stop_server()
        self._registry.clear()
        gc.collect()

    # ── Server lifecycle ───────────────────────────────────

    def _start_server(self):
        if self.running:
            return
        self.running = True
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.host, self.port))
            self._socket.listen(1)
            self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self._server_thread.start()
            print(f"Isaac Sim MCP server started on {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to start server: {e}")
            self._stop_server()

    def _stop_server(self):
        self.running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)
        self._server_thread = None
        print("Isaac Sim MCP server stopped")

    # ── Connection handling ────────────────────────────────

    def _server_loop(self):
        self._socket.settimeout(1.0)
        while self.running:
            try:
                client, address = self._socket.accept()
                print(f"Connected to client: {address}")
                threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
                    time.sleep(0.5)

    def _handle_client(self, client):
        client.settimeout(None)
        buffer = b""
        try:
            while self.running:
                data = client.recv(16384)
                if not data:
                    break
                buffer += data
                try:
                    command = json.loads(buffer.decode("utf-8"))
                    buffer = b""
                    self._dispatch_command(client, command)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            print(f"Error in client handler: {e}")
        finally:
            client.close()

    def _dispatch_command(self, client, command):
        async def execute_wrapper():
            try:
                response = self._execute_command(command)
                response_json = json.dumps(response)
                try:
                    client.sendall(response_json.encode("utf-8"))
                except Exception:
                    print("Failed to send response — client disconnected")
            except Exception as e:
                traceback.print_exc()
                try:
                    client.sendall(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
                except Exception:
                    pass

        from omni.kit.async_engine import run_coroutine
        run_coroutine(execute_wrapper())

    # ── Command routing ────────────────────────────────────

    def _execute_command(self, command):
        cmd_type = command.get("type", "")
        params = command.get("params", {})
        handler = self._registry.get(cmd_type)
        if handler:
            try:
                result = handler(**params)
                if result and result.get("status") == "success":
                    return {"status": "success", "result": result}
                else:
                    return {"status": "error", "message": result.get("message", "Unknown error") if result else "No result"}
            except Exception as e:
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": f"Unknown command: {cmd_type}"}
```

- [ ] **Step 2: Verify extension.py parses correctly**

```bash
python -c "import ast; ast.parse(open('isaac.sim.mcp_extension/isaac_sim_mcp_extension/extension.py').read()); print('extension.py parses OK')"
```

Expected: `extension.py parses OK`

- [ ] **Step 3: Commit**

```bash
git add isaac.sim.mcp_extension/isaac_sim_mcp_extension/extension.py
git commit -m "refactor: rewrite extension.py as slim registry-based command router"
```

---

## Task 8: Run all tests and final validation

**Files:**
- Read: all test files

- [ ] **Step 1: Run all tests**

```bash
cd /home/user/Documents/GitHub/isaac-sim-mcp
python -m pytest tests/ -v
```

Expected: All tests PASS:
- `test_handler_structure.py::test_adapter_base_has_all_abstract_methods` — PASS
- `test_handler_structure.py::test_v5_adapter_implements_all_methods` — PASS
- `test_handler_structure.py::test_all_handler_modules_have_register` — PASS
- `test_connection.py::test_connection_module_exists` — PASS
- `test_connection.py::test_connection_has_required_classes_and_functions` — PASS
- `test_tool_registration.py::test_all_tool_modules_exist` — PASS
- `test_tool_registration.py::test_all_tool_modules_have_register_tools` — PASS
- `test_tool_registration.py::test_init_imports_all_modules` — PASS

- [ ] **Step 2: Verify all Python files parse without syntax errors**

```bash
find isaac_mcp isaac.sim.mcp_extension/isaac_sim_mcp_extension -name "*.py" | while read f; do python -c "import ast; ast.parse(open('$f').read())" && echo "OK: $f" || echo "FAIL: $f"; done
```

Expected: All files print `OK`.

- [ ] **Step 3: Commit any fixes if needed, then tag**

```bash
git add -A
git status
# Only commit if there are changes
git diff --cached --quiet || git commit -m "fix: address any issues found during validation"
```

---

## Task 9: Update README and documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the MCP Tools section in README.md**

Find the existing `## MCP Tools` section in `README.md` and replace it with the updated tool catalog that reflects the new modular structure and all 31 tools. Group them by category (Scene, Objects, Lighting, Robots, Sensors, Materials, Assets, Simulation) with brief descriptions matching the tool docstrings.

- [ ] **Step 2: Update the MCP server configuration section**

The MCP server command stays the same (`uv run ~/Documents/isaac-sim-mcp/isaac_mcp/server.py`). No changes needed to the config JSON.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README with new modular tool catalog"
```

---

## Summary

| Task | Description | Files | Est. Steps |
|------|-------------|-------|------------|
| 1 | Directory structure & init files | 4 new | 5 |
| 2 | Adapter layer (base + v5) | 3 new | 5 |
| 3 | Extract connection module | 2 new | 5 |
| 4 | All 8 handler modules | 8 new | 10 |
| 5 | All 8 tool modules | 9 new | 11 |
| 6 | Rewrite server.py | 1 modify | 3 |
| 7 | Rewrite extension.py | 1 modify | 3 |
| 8 | Run all tests | — | 3 |
| 9 | Update README | 1 modify | 3 |
| **Total** | | **37 files** | **48 steps** |
