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

    def discover_environments(self) -> Dict[str, Dict[str, str]]:
        """Scan the Isaac Sim asset server for available environment USD files."""
        import omni.client
        from isaacsim.storage.native import get_assets_root_path

        root = get_assets_root_path()
        discovered: Dict[str, Dict[str, str]] = {}

        search_bases = ["/Isaac/Environments/", "/NVIDIA/Assets/Scenes/Templates/"]
        for base in search_bases:
            result, entries = omni.client.list(root + base)
            if result != omni.client.Result.OK:
                continue
            for entry in entries:
                name = entry.relative_path.rstrip("/")
                dir_path = root + base + name + "/"
                r2, files = omni.client.list(dir_path)
                if r2 != omni.client.Result.OK:
                    continue
                # Find USD files at this level
                for f in files:
                    if f.relative_path.endswith(".usd") or f.relative_path.endswith(".usda"):
                        key = name.lower().replace(" ", "_")
                        if key not in discovered:
                            discovered[key] = {
                                "asset_path": base + name + "/" + f.relative_path,
                                "description": name.replace("_", " "),
                            }
                        break
                # Also check one level deeper for nested envs
                for f in files:
                    subname = f.relative_path.rstrip("/")
                    r3, subfiles = omni.client.list(dir_path + subname + "/")
                    if r3 != omni.client.Result.OK:
                        continue
                    for sf in subfiles:
                        if sf.relative_path.endswith(".usd") or sf.relative_path.endswith(".usda"):
                            key = f"{name}_{subname}".lower().replace(" ", "_")
                            if key not in discovered:
                                discovered[key] = {
                                    "asset_path": base + name + "/" + subname + "/" + sf.relative_path,
                                    "description": f"{name} {subname}".replace("_", " "),
                                }
                            break
        return discovered

    def load_environment(self, env_path: str, prim_path: str = "/Environment") -> None:
        from isaacsim.core.utils.stage import add_reference_to_stage
        add_reference_to_stage(env_path, prim_path)

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
        xformable.ClearXformOpOrder()
        if position is not None:
            xformable.AddTranslateOp(precision=UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*position))
        if rotation is not None:
            xformable.AddRotateXYZOp(precision=UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*rotation))
        if scale is not None:
            xformable.AddScaleOp(precision=UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*scale))

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

    def discover_robots(self) -> Dict[str, Dict[str, str]]:
        """Scan the Isaac Sim asset server for all available robot USD files."""
        import omni.client
        from isaacsim.storage.native import get_assets_root_path

        root = get_assets_root_path()
        robots_base = root + "/Isaac/Robots/"
        discovered: Dict[str, Dict[str, str]] = {}

        result, manufacturers = omni.client.list(robots_base)
        if result != omni.client.Result.OK:
            return discovered

        for mfr_entry in manufacturers:
            mfr_name = mfr_entry.relative_path.rstrip("/")
            mfr_path = robots_base + mfr_name + "/"

            result2, models = omni.client.list(mfr_path)
            if result2 != omni.client.Result.OK:
                continue

            for model_entry in models:
                model_name = model_entry.relative_path.rstrip("/")
                model_path = mfr_path + model_name + "/"

                # Look for USD files directly in the model directory
                result3, files = omni.client.list(model_path)
                if result3 != omni.client.Result.OK:
                    continue

                for file_entry in files:
                    fname = file_entry.relative_path
                    if not (fname.endswith(".usd") or fname.endswith(".usda")):
                        continue
                    # Skip variants with suffixes like _physx_lidar, _with_arm
                    base_name = fname.rsplit(".", 1)[0]
                    asset_rel = f"/Isaac/Robots/{mfr_name}/{model_name}/{fname}"

                    # Use lowercase model name as key, prefer shorter/simpler names
                    key = model_name.lower().replace(" ", "_")
                    if key in discovered:
                        # Keep the simpler filename (shorter name wins)
                        if len(fname) < len(discovered[key]["asset_path"].split("/")[-1]):
                            discovered[key]["asset_path"] = asset_rel
                    else:
                        discovered[key] = {
                            "asset_path": asset_rel,
                            "description": f"{mfr_name} {model_name}",
                            "manufacturer": mfr_name,
                        }

        return discovered

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

    def get_joint_config(self, prim_path: str) -> Dict[str, Any]:
        from pxr import UsdPhysics, Usd
        from isaacsim.core.prims import SingleArticulation

        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")

        # Get current joint positions via articulation
        art = SingleArticulation(prim_path=prim_path)
        joint_names = art.dof_names if art.dof_names else []
        current_positions = art.get_joint_positions()
        current_pos_list = current_positions.tolist() if current_positions is not None else []

        joints_info = []

        # Walk descendants to find joint prims
        for desc in Usd.PrimRange(prim):
            if desc.IsA(UsdPhysics.RevoluteJoint) or desc.IsA(UsdPhysics.PrismaticJoint):
                joint_data: Dict[str, Any] = {"name": desc.GetName()}

                if desc.IsA(UsdPhysics.RevoluteJoint):
                    joint_data["type"] = "revolute"
                    joint_api = UsdPhysics.RevoluteJoint(desc)
                    lower_attr = joint_api.GetLowerLimitAttr()
                    upper_attr = joint_api.GetUpperLimitAttr()
                else:
                    joint_data["type"] = "prismatic"
                    joint_api = UsdPhysics.PrismaticJoint(desc)
                    lower_attr = joint_api.GetLowerLimitAttr()
                    upper_attr = joint_api.GetUpperLimitAttr()

                joint_data["lower_limit"] = lower_attr.Get() if lower_attr else None
                joint_data["upper_limit"] = upper_attr.Get() if upper_attr else None

                # Get drive config
                for drive_type in ["angular", "linear"]:
                    drive_api = UsdPhysics.DriveAPI.Get(desc, drive_type)
                    if drive_api:
                        joint_data["drive_type"] = drive_type
                        stiffness_attr = drive_api.GetStiffnessAttr()
                        damping_attr = drive_api.GetDampingAttr()
                        target_attr = drive_api.GetTargetPositionAttr()
                        joint_data["stiffness"] = stiffness_attr.Get() if stiffness_attr else None
                        joint_data["damping"] = damping_attr.Get() if damping_attr else None
                        joint_data["target_position"] = target_attr.Get() if target_attr else None
                        break

                # Match actual position from articulation if possible
                joint_name = desc.GetName()
                if joint_name in joint_names:
                    idx = joint_names.index(joint_name)
                    if idx < len(current_pos_list):
                        joint_data["actual_position"] = current_pos_list[idx]
                        if joint_data.get("target_position") is not None:
                            joint_data["position_error"] = joint_data["target_position"] - current_pos_list[idx]

                joints_info.append(joint_data)

        return {
            "prim_path": prim_path,
            "joint_count": len(joints_info),
            "joints": joints_info,
        }

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

    def get_physics_state(self, prim_path: str) -> Dict[str, Any]:
        from pxr import UsdPhysics, Gf
        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")

        result: Dict[str, Any] = {"prim_path": prim_path}

        # Check rigid body API
        has_rb = prim.HasAPI(UsdPhysics.RigidBodyAPI)
        result["has_rigid_body"] = has_rb

        if has_rb:
            rb = UsdPhysics.RigidBodyAPI(prim)
            kinematic_attr = rb.GetKinematicEnabledAttr()
            result["is_kinematic"] = kinematic_attr.Get() if kinematic_attr else False

        # Check mass
        has_mass = prim.HasAPI(UsdPhysics.MassAPI)
        if has_mass:
            mass_api = UsdPhysics.MassAPI(prim)
            mass_attr = mass_api.GetMassAttr()
            result["mass"] = mass_attr.Get() if mass_attr else None

        # Check collision
        has_collision = prim.HasAPI(UsdPhysics.CollisionAPI)
        result["collision_enabled"] = has_collision

        # Get velocities via PhysX if simulation is running
        try:
            import omni.physx
            physx_interface = omni.physx.get_physx_interface()
            rigid_body_handle = physx_interface.get_rigidbody_transformation(prim_path)
            if rigid_body_handle:
                result["linear_velocity"] = list(rigid_body_handle.get("linear_velocity", [0, 0, 0]))
                result["angular_velocity"] = list(rigid_body_handle.get("angular_velocity", [0, 0, 0]))
        except Exception:
            # Velocities not available when simulation isn't running
            if has_rb:
                result["linear_velocity"] = [0.0, 0.0, 0.0]
                result["angular_velocity"] = [0.0, 0.0, 0.0]

        # Get contact info if available
        try:
            from omni.physx import get_physx_scene_query_interface
            contacts = []
            result["contacts"] = contacts
        except Exception:
            result["contacts"] = []

        return result

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
        import os
        if not os.path.isfile(urdf_path):
            raise FileNotFoundError(f"URDF file not found: {urdf_path}")
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

    def step(self, num_steps: int = 1, observe_prims: Optional[List[str]] = None,
             observe_joints: Optional[List[str]] = None) -> Dict[str, Any]:
        import omni.kit.app

        for _ in range(num_steps):
            omni.kit.app.get_app().update()

        result: Dict[str, Any] = {"stepped": num_steps}

        # Observe prim states
        if observe_prims:
            from pxr import UsdPhysics
            prim_states = []
            stage = self.get_stage()
            for path in observe_prims:
                prim = stage.GetPrimAtPath(path)
                if not prim.IsValid():
                    prim_states.append({"prim_path": path, "error": "Prim not found"})
                    continue
                state: Dict[str, Any] = {"prim_path": path}
                transform = self.get_prim_transform(path)
                state["position"] = transform.get("position", [0, 0, 0])
                # Add velocity if rigid body
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    try:
                        physics_state = self.get_physics_state(path)
                        state["linear_velocity"] = physics_state.get("linear_velocity", [0, 0, 0])
                        state["angular_velocity"] = physics_state.get("angular_velocity", [0, 0, 0])
                    except Exception:
                        pass
                prim_states.append(state)
            result["prim_states"] = prim_states

        # Observe joint states
        if observe_joints:
            joint_states = []
            for path in observe_joints:
                try:
                    positions = self.get_joint_positions(path)
                    from isaacsim.core.prims import SingleArticulation
                    art = SingleArticulation(prim_path=path)
                    names = art.dof_names if art.dof_names else []
                    joints_dict = dict(zip(names, positions)) if names else {"positions": positions}
                    joint_states.append({"prim_path": path, "joints": joints_dict})
                except Exception as e:
                    joint_states.append({"prim_path": path, "error": str(e)})
            result["joint_states"] = joint_states

        return result

    def get_simulation_state(self) -> Dict[str, Any]:
        import omni.timeline

        timeline = omni.timeline.get_timeline_interface()
        is_playing = timeline.is_playing()
        is_stopped = timeline.is_stopped()

        if is_playing:
            state = "playing"
        elif is_stopped:
            state = "stopped"
        else:
            state = "paused"

        current_time = timeline.get_current_time()
        # Get physics dt from physics scene if available
        from pxr import UsdPhysics
        stage = self.get_stage()
        physics_dt = 1.0 / 60.0  # default
        for prim in stage.Traverse():
            if prim.HasAPI(UsdPhysics.Scene):
                time_step_attr = prim.GetAttribute("physxScene:timeStepsPerSecond")
                if time_step_attr and time_step_attr.Get():
                    steps_per_sec = time_step_attr.Get()
                    if steps_per_sec > 0:
                        physics_dt = 1.0 / steps_per_sec
                break

        return {
            "timeline_state": state,
            "current_time": current_time,
            "physics_dt": physics_dt,
        }

    def execute_script(self, code: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        import sys
        import io
        import omni
        import carb
        from pxr import Usd, UsdGeom, Sdf, Gf

        # Auto-add cwd to sys.path
        if cwd and cwd not in sys.path:
            sys.path.insert(0, cwd)

        local_ns = {"omni": omni, "carb": carb, "Usd": Usd, "UsdGeom": UsdGeom, "Sdf": Sdf, "Gf": Gf}

        # Capture stdout/stderr
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = captured_out = io.StringIO()
        sys.stderr = captured_err = io.StringIO()
        try:
            exec(code, local_ns)
            return {
                "status": "success",
                "message": "Script executed successfully",
                "stdout": captured_out.getvalue(),
                "stderr": captured_err.getvalue(),
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc(),
                "stdout": captured_out.getvalue(),
                "stderr": captured_err.getvalue(),
            }
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr

    def reload_script(self, file_path: str, module_name: Optional[str] = None) -> Dict[str, Any]:
        import sys
        import os
        import io
        import importlib

        # Auto-add parent directory to sys.path
        parent_dir = os.path.dirname(os.path.abspath(file_path))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        # Capture stdout/stderr
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = captured_out = io.StringIO()
        sys.stderr = captured_err = io.StringIO()
        try:
            if module_name:
                # Reload existing module or import for first time
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                    msg = f"Module '{module_name}' reloaded successfully"
                else:
                    module = importlib.import_module(module_name)
                    msg = f"Module '{module_name}' imported successfully"
            else:
                # Execute file contents (hot-patch)
                if not os.path.isfile(file_path):
                    return {"status": "error", "message": f"File not found: {file_path}"}
                with open(file_path, "r") as f:
                    code = f.read()
                import omni
                import carb
                from pxr import Usd, UsdGeom, Sdf, Gf
                local_ns = {"omni": omni, "carb": carb, "Usd": Usd, "UsdGeom": UsdGeom,
                             "Sdf": Sdf, "Gf": Gf, "__file__": file_path}
                exec(code, local_ns)
                msg = f"Script '{os.path.basename(file_path)}' executed successfully"

            return {
                "status": "success",
                "message": msg,
                "stdout": captured_out.getvalue(),
                "stderr": captured_err.getvalue(),
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc(),
                "stdout": captured_out.getvalue(),
                "stderr": captured_err.getvalue(),
            }
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
