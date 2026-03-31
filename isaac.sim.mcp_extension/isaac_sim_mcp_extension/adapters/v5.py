"""Isaac Sim 5.1.0 adapter implementation."""

from __future__ import annotations

import traceback
import numpy as np
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

from .base import IsaacAdapterBase

if TYPE_CHECKING:
    from pxr import Usd


class IsaacAdapterV5(IsaacAdapterBase):
    """Adapter for Isaac Sim 5.1.0 (isaacsim.* namespace)."""

    # ── Scene ──────────────────────────────────────────────

    def get_stage(self) -> Usd.Stage:
        import omni.usd
        return omni.usd.get_context().get_stage()

    def get_assets_root_path(self) -> str:
        from isaacsim.storage.native import get_assets_root_path
        return get_assets_root_path()

    # ── Prims ──────────────────────────────────────────────

    def create_prim(self, prim_path: str, prim_type: str = "Xform", **kwargs) -> Usd.Prim:
        from isaacsim.core.utils.prims import create_prim
        return create_prim(prim_path, prim_type, **kwargs)

    def delete_prim(self, prim_path: str) -> bool:
        import omni.kit.commands
        omni.kit.commands.execute("DeletePrims", paths=[prim_path])
        return True

    def add_reference_to_stage(self, usd_path: str, prim_path: str) -> Usd.Prim:
        from isaacsim.core.utils.stage import add_reference_to_stage
        return add_reference_to_stage(usd_path, prim_path)

    def set_prim_transform(
        self,
        prim_path: str,
        position: Optional[Sequence[float]] = None,
        rotation: Optional[Sequence[float]] = None,
        scale: Optional[Sequence[float]] = None,
    ) -> None:
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

    def list_prims(self, root_path: str = "/", prim_type: Optional[str] = None) -> List[Dict[str, str]]:
        stage = self.get_stage()
        root = stage.GetPrimAtPath(root_path)
        results: List[Dict[str, str]] = []
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

    def create_xform_prim(self, prim_path: str) -> Any:
        from isaacsim.core.prims import SingleXFormPrim
        return SingleXFormPrim(prim_path=prim_path)

    def create_articulation(self, prim_path: str, name: str) -> Any:
        from isaacsim.core.prims import SingleArticulation
        return SingleArticulation(prim_path=prim_path, name=name)

    def get_robot_joint_info(self, prim_path: str) -> Dict[str, Any]:
        from isaacsim.core.prims import SingleArticulation
        art = SingleArticulation(prim_path=prim_path)
        return {
            "joint_names": art.dof_names if art.dof_names else [],
            "num_dof": art.num_dof if art.num_dof else 0,
        }

    def set_joint_positions(
        self,
        prim_path: str,
        positions: Sequence[float],
        joint_indices: Optional[List[int]] = None,
    ) -> None:
        from isaacsim.core.prims import SingleArticulation
        from isaacsim.core.utils.types import ArticulationAction
        art = SingleArticulation(prim_path=prim_path)
        action = ArticulationAction(
            joint_positions=np.array(positions),
            joint_indices=np.array(joint_indices) if joint_indices else None,
        )
        controller = art.get_articulation_controller()
        controller.apply_action(action)

    def get_joint_positions(self, prim_path: str) -> List[float]:
        from isaacsim.core.prims import SingleArticulation
        art = SingleArticulation(prim_path=prim_path)
        positions = art.get_joint_positions()
        return positions.tolist() if positions is not None else []

    # ── Physics ────────────────────────────────────────────

    def create_world(self, **kwargs) -> Any:
        from isaacsim.core.api import World
        return World(**kwargs)

    def create_simulation_context(self, **kwargs) -> Any:
        from isaacsim.core.api import SimulationContext
        return SimulationContext(**kwargs)

    def create_physics_scene(self, gravity: Optional[Sequence[float]] = None, scene_name: str = "PhysicsScene") -> str:
        import omni.kit.commands
        scene_path = f"/World/{scene_name}"
        omni.kit.commands.execute("CreatePrim", prim_path=scene_path, prim_type="PhysicsScene")
        return scene_path

    # ── Sensors ────────────────────────────────────────────

    def create_camera(self, prim_path: str, resolution: Tuple[int, int] = (1280, 720), **kwargs) -> Any:
        from isaacsim.sensors.camera import Camera
        return Camera(prim_path=prim_path, resolution=resolution, **kwargs)

    def capture_camera_image(self, prim_path: str) -> np.ndarray:
        from isaacsim.sensors.camera import Camera
        cam = Camera(prim_path=prim_path)
        return cam.get_rgba()

    def create_lidar(self, prim_path: str, config: Optional[str] = None, **kwargs) -> Any:
        from isaacsim.sensors.rtx import LidarRtx
        return LidarRtx(prim_path=prim_path, config=config or "Example_Rotary", **kwargs)

    def get_lidar_point_cloud(self, prim_path: str) -> np.ndarray:
        from isaacsim.sensors.rtx import LidarRtx
        lidar = LidarRtx(prim_path=prim_path)
        return lidar.get_point_cloud()

    # ── Materials ──────────────────────────────────────────

    def create_pbr_material(
        self,
        prim_path: str,
        color: Optional[Sequence[float]] = None,
        roughness: float = 0.5,
        metallic: float = 0.0,
    ) -> Any:
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

    def create_physics_material(
        self,
        prim_path: str,
        static_friction: float = 0.5,
        dynamic_friction: float = 0.5,
        restitution: float = 0.0,
    ) -> Any:
        from pxr import UsdPhysics
        stage = self.get_stage()
        material = UsdPhysics.MaterialAPI.Apply(stage.DefinePrim(prim_path))
        material.CreateStaticFrictionAttr(static_friction)
        material.CreateDynamicFrictionAttr(dynamic_friction)
        material.CreateRestitutionAttr(restitution)
        return material

    def apply_material(self, material_path: str, target_prim_path: str) -> None:
        from pxr import UsdShade
        stage = self.get_stage()
        material = UsdShade.Material(stage.GetPrimAtPath(material_path))
        target = stage.GetPrimAtPath(target_prim_path)
        UsdShade.MaterialBindingAPI(target).Bind(material)

    # ── Lighting ───────────────────────────────────────────

    def create_light(
        self,
        light_type: str,
        prim_path: str,
        intensity: float = 1000.0,
        color: Optional[Sequence[float]] = None,
        **kwargs,
    ) -> Any:
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

    def modify_light(
        self,
        prim_path: str,
        intensity: Optional[float] = None,
        color: Optional[Sequence[float]] = None,
    ) -> None:
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

    def clone_prim(self, source_path: str, target_path: str) -> None:
        import omni.kit.commands
        omni.kit.commands.execute("CopyPrim", path_from=source_path, path_to=target_path)

    def import_urdf(self, urdf_path: str, prim_path: str = "/World/robot", **kwargs) -> Any:
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

    def play(self) -> None:
        import omni.timeline
        omni.timeline.get_timeline_interface().play()

    def pause(self) -> None:
        import omni.timeline
        omni.timeline.get_timeline_interface().pause()

    def stop(self) -> None:
        import omni.timeline
        omni.timeline.get_timeline_interface().stop()

    def step(self, num_steps: int = 1) -> None:
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
