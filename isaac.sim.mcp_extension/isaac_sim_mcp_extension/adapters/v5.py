# MIT License
#
# Copyright (c) 2023-2025 omni-mcp
# Copyright (c) 2026 whats2000
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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

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
        from pxr import Gf, UsdGeom

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
        from pxr import UsdGeom

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
        info: Dict[str, Any] = {
            "path": prim_path,
            "type": prim.GetTypeName(),
            "transform": transform,
            "children": children,
        }
        if prim.GetTypeName() in ("Cube", "Sphere", "Cylinder", "Cone", "Capsule"):
            try:
                actual_size, _bbox = self.get_prim_actual_size(prim_path)
                info["actual_size"] = actual_size
            except Exception:
                pass
        return info

    def get_prim_actual_size(self, prim_path: str) -> Tuple[List[float], Tuple[List[float], List[float]]]:
        """Return actual dimensions and bounding box for a geometric prim."""
        from pxr import UsdGeom

        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")

        prim_type = prim.GetTypeName()

        # Read scale from xform
        xformable = UsdGeom.Xformable(prim)
        local_transform = xformable.GetLocalTransformation()
        # Extract scale from the matrix diagonal (assuming uniform or axis-aligned scale)
        scale = [
            float(local_transform.GetRow3(0).GetLength()),
            float(local_transform.GetRow3(1).GetLength()),
            float(local_transform.GetRow3(2).GetLength()),
        ]

        if prim_type == "Cube":
            geom = UsdGeom.Cube(prim)
            size_attr = geom.GetSizeAttr()
            size = float(size_attr.Get()) if size_attr and size_attr.Get() is not None else 1.0
            dims = [size * scale[0], size * scale[1], size * scale[2]]
        elif prim_type == "Sphere":
            geom = UsdGeom.Sphere(prim)
            radius_attr = geom.GetRadiusAttr()
            radius = float(radius_attr.Get()) if radius_attr and radius_attr.Get() is not None else 0.5
            diameter = radius * 2.0
            dims = [diameter * scale[0], diameter * scale[1], diameter * scale[2]]
        elif prim_type == "Cylinder":
            geom = UsdGeom.Cylinder(prim)
            radius_attr = geom.GetRadiusAttr()
            height_attr = geom.GetHeightAttr()
            axis_attr = geom.GetAxisAttr()
            radius = float(radius_attr.Get()) if radius_attr and radius_attr.Get() is not None else 0.5
            height = float(height_attr.Get()) if height_attr and height_attr.Get() is not None else 1.0
            axis = axis_attr.Get() if axis_attr and axis_attr.Get() is not None else "Z"
            diameter = radius * 2.0
            if axis == "X":
                dims = [height * scale[0], diameter * scale[1], diameter * scale[2]]
            elif axis == "Y":
                dims = [diameter * scale[0], height * scale[1], diameter * scale[2]]
            else:  # Z (default)
                dims = [diameter * scale[0], diameter * scale[1], height * scale[2]]
        elif prim_type == "Cone":
            geom = UsdGeom.Cone(prim)
            radius_attr = geom.GetRadiusAttr()
            height_attr = geom.GetHeightAttr()
            axis_attr = geom.GetAxisAttr()
            radius = float(radius_attr.Get()) if radius_attr and radius_attr.Get() is not None else 0.5
            height = float(height_attr.Get()) if height_attr and height_attr.Get() is not None else 1.0
            axis = axis_attr.Get() if axis_attr and axis_attr.Get() is not None else "Z"
            diameter = radius * 2.0
            if axis == "X":
                dims = [height * scale[0], diameter * scale[1], diameter * scale[2]]
            elif axis == "Y":
                dims = [diameter * scale[0], height * scale[1], diameter * scale[2]]
            else:  # Z (default)
                dims = [diameter * scale[0], diameter * scale[1], height * scale[2]]
        elif prim_type == "Capsule":
            geom = UsdGeom.Capsule(prim)
            radius_attr = geom.GetRadiusAttr()
            height_attr = geom.GetHeightAttr()
            radius = float(radius_attr.Get()) if radius_attr and radius_attr.Get() is not None else 0.5
            height = float(height_attr.Get()) if height_attr and height_attr.Get() is not None else 1.0
            total_height = height + 2.0 * radius
            diameter = radius * 2.0
            dims = [diameter * scale[0], diameter * scale[1], total_height * scale[2]]
        else:
            raise ValueError(f"Unsupported prim type for size calculation: {prim_type}")

        # Compute world-space position for bounding box
        from pxr import Usd
        world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        translation = world_transform.ExtractTranslation()
        pos = [float(translation[0]), float(translation[1]), float(translation[2])]
        half = [d / 2.0 for d in dims]
        bbox_min = [pos[0] - half[0], pos[1] - half[1], pos[2] - half[2]]
        bbox_max = [pos[0] + half[0], pos[1] + half[1], pos[2] + half[2]]

        return dims, (bbox_min, bbox_max)

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
                    _base_name = fname.rsplit(".", 1)[0]
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
        from pxr import Usd, UsdPhysics

        # Try to get joint info via articulation API (requires running sim)
        joint_names: List[str] = []
        num_dof = 0
        art = SingleArticulation(prim_path=prim_path)
        try:
            art.initialize()
            joint_names = list(art.dof_names) if art.dof_names else []
            num_dof = art.num_dof if art.num_dof else 0
        except Exception:
            pass

        # Fallback: discover joints by traversing USD stage
        stage = self.get_stage()
        root_prim = stage.GetPrimAtPath(prim_path)
        if not joint_names and root_prim.IsValid():
            for desc in Usd.PrimRange(root_prim):
                if desc.IsA(UsdPhysics.RevoluteJoint) or desc.IsA(UsdPhysics.PrismaticJoint):
                    joint_names.append(desc.GetName())
            num_dof = len(joint_names)

        joint_limits = []
        for jname in joint_names:
            limit_entry: Dict[str, Any] = {"name": jname}
            for desc in Usd.PrimRange(root_prim):
                if desc.GetName() != jname:
                    continue
                if desc.IsA(UsdPhysics.RevoluteJoint):
                    rev = UsdPhysics.RevoluteJoint(desc)
                    lo = rev.GetLowerLimitAttr().Get()
                    hi = rev.GetUpperLimitAttr().Get()
                    limit_entry["type"] = "revolute"
                    limit_entry["lower"] = float(lo) if lo is not None else None
                    limit_entry["upper"] = float(hi) if hi is not None else None
                    limit_entry["units"] = "degrees"
                    break
                if desc.IsA(UsdPhysics.PrismaticJoint):
                    pris = UsdPhysics.PrismaticJoint(desc)
                    lo = pris.GetLowerLimitAttr().Get()
                    hi = pris.GetUpperLimitAttr().Get()
                    limit_entry["type"] = "prismatic"
                    limit_entry["lower"] = float(lo) if lo is not None else None
                    limit_entry["upper"] = float(hi) if hi is not None else None
                    limit_entry["units"] = "meters"
                    break
            joint_limits.append(limit_entry)

        return {
            "joint_names": joint_names,
            "num_dof": num_dof,
            "joint_limits": joint_limits,
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
        try:
            art.initialize()
            action = ArticulationAction(
                joint_positions=np.array(positions),
                joint_indices=np.array(joint_indices) if joint_indices else None,
            )
            controller = art.get_articulation_controller()
            controller.apply_action(action)
        except Exception:
            # Fallback: set USD drive targets directly (works when sim is stopped)
            self._set_joint_drive_targets(prim_path, positions, joint_indices)

    def _set_joint_drive_targets(
        self,
        prim_path: str,
        positions: Sequence[float],
        joint_indices: Optional[List[int]] = None,
    ) -> None:
        """Set joint drive targets via USD API — works regardless of simulation state."""
        from pxr import Usd, UsdPhysics

        stage = self.get_stage()
        root_prim = stage.GetPrimAtPath(prim_path)
        if not root_prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")

        # Collect all joints under the articulation
        joints = []
        for desc in Usd.PrimRange(root_prim):
            if desc.IsA(UsdPhysics.RevoluteJoint) or desc.IsA(UsdPhysics.PrismaticJoint):
                joints.append(desc)

        if joint_indices is not None:
            targets = list(zip(joint_indices, positions))
        else:
            targets = list(enumerate(positions))

        for idx, value in targets:
            if idx >= len(joints):
                continue
            joint_prim = joints[idx]
            is_revolute = joint_prim.IsA(UsdPhysics.RevoluteJoint)
            drive_type = "angular" if is_revolute else "linear"
            drive = UsdPhysics.DriveAPI.Get(joint_prim, drive_type)
            if not drive:
                drive = UsdPhysics.DriveAPI.Apply(joint_prim, drive_type)
            if is_revolute:
                drive.GetTargetPositionAttr().Set(float(np.degrees(value)))
            else:
                # Prismatic joints: positions in meters, USD targets in cm
                drive.GetTargetPositionAttr().Set(float(value * 100.0))

    def _get_joint_names(self, prim_path: str) -> List[str]:
        """Get joint names, trying articulation API first then USD fallback."""
        from isaacsim.core.prims import SingleArticulation

        art = SingleArticulation(prim_path=prim_path)
        try:
            art.initialize()
            if art.dof_names:
                return list(art.dof_names)
        except Exception:
            pass

        # Fallback: traverse USD
        from pxr import Usd, UsdPhysics

        stage = self.get_stage()
        root_prim = stage.GetPrimAtPath(prim_path)
        if not root_prim.IsValid():
            return []
        names: List[str] = []
        for desc in Usd.PrimRange(root_prim):
            if desc.IsA(UsdPhysics.RevoluteJoint) or desc.IsA(UsdPhysics.PrismaticJoint):
                names.append(desc.GetName())
        return names

    def get_joint_positions(self, prim_path: str) -> List[float]:
        from isaacsim.core.prims import SingleArticulation

        art = SingleArticulation(prim_path=prim_path)
        try:
            art.initialize()
            positions = art.get_joint_positions()
            if positions is not None:
                return positions.tolist()
        except Exception:
            pass

        # Fallback: read drive target positions from USD
        from pxr import Usd, UsdPhysics

        stage = self.get_stage()
        root_prim = stage.GetPrimAtPath(prim_path)
        if not root_prim.IsValid():
            return []
        positions_list: List[float] = []
        for desc in Usd.PrimRange(root_prim):
            if not (desc.IsA(UsdPhysics.RevoluteJoint) or desc.IsA(UsdPhysics.PrismaticJoint)):
                continue
            is_revolute = desc.IsA(UsdPhysics.RevoluteJoint)
            drive_type = "angular" if is_revolute else "linear"
            drive = UsdPhysics.DriveAPI.Get(desc, drive_type)
            if drive:
                target = drive.GetTargetPositionAttr().Get()
                if target is not None:
                    if is_revolute:
                        positions_list.append(float(np.radians(target)))
                    else:
                        positions_list.append(float(target / 100.0))
                else:
                    positions_list.append(0.0)
            else:
                positions_list.append(0.0)
        return positions_list

    def get_joint_config(self, prim_path: str) -> Dict[str, Any]:
        from isaacsim.core.prims import SingleArticulation
        from pxr import Usd, UsdPhysics

        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")

        # Get current joint positions and names via articulation (requires running sim)
        joint_names = self._get_joint_names(prim_path)
        current_pos_list = self.get_joint_positions(prim_path)

        # Get runtime target positions (from applied actions, not USD defaults)
        art = SingleArticulation(prim_path=prim_path)
        runtime_targets: List[float] = []
        try:
            art.initialize()
            applied_action = art.get_applied_action()
            if applied_action and applied_action.joint_positions is not None:
                runtime_targets = applied_action.joint_positions.tolist()
        except Exception:
            pass  # Fall back to USD values if articulation controller unavailable

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
                        # USD default as fallback
                        joint_data["target_position"] = target_attr.Get() if target_attr else None
                        break

                # Match actual position from articulation if possible
                joint_name = desc.GetName()
                if joint_name in joint_names:
                    idx = joint_names.index(joint_name)
                    if idx < len(current_pos_list):
                        joint_data["actual_position"] = current_pos_list[idx]

                    # Override target_position with runtime value if available
                    if idx < len(runtime_targets):
                        joint_data["target_position"] = float(runtime_targets[idx])

                    # Calculate position_error using (possibly runtime) target
                    if joint_data.get("target_position") is not None and "actual_position" in joint_data:
                        joint_data["position_error"] = joint_data["target_position"] - joint_data["actual_position"]

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
        from pxr import UsdPhysics

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

        # Get velocities from USD RigidBodyAPI attributes (updated during simulation)
        if has_rb:
            try:
                rb_api = UsdPhysics.RigidBodyAPI(prim)
                vel_attr = rb_api.GetVelocityAttr()
                ang_vel_attr = rb_api.GetAngularVelocityAttr()
                vel = vel_attr.Get() if vel_attr else None
                ang_vel = ang_vel_attr.Get() if ang_vel_attr else None
                result["linear_velocity"] = list(vel) if vel else [0.0, 0.0, 0.0]
                result["angular_velocity"] = list(ang_vel) if ang_vel else [0.0, 0.0, 0.0]
            except Exception:
                result["linear_velocity"] = [0.0, 0.0, 0.0]
                result["angular_velocity"] = [0.0, 0.0, 0.0]

        # Get contact info if available
        try:
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
        from pxr import Gf, Sdf, UsdShade

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
        from pxr import Gf, UsdLux

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
        from pxr import Gf

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

    def step(
        self, num_steps: int = 1, observe_prims: Optional[List[str]] = None, observe_joints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
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
                    names = self._get_joint_names(path)
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
        import io
        import sys

        import carb
        import omni
        from pxr import Gf, Sdf, Usd, UsdGeom

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
        import importlib
        import io
        import os
        import sys

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
                    _module = importlib.reload(sys.modules[module_name])
                    msg = f"Module '{module_name}' reloaded successfully"
                else:
                    _module = importlib.import_module(module_name)
                    msg = f"Module '{module_name}' imported successfully"
            else:
                # Execute file contents (hot-patch)
                if not os.path.isfile(file_path):
                    return {"status": "error", "message": f"File not found: {file_path}"}
                with open(file_path, "r") as f:
                    code = f.read()
                import carb
                import omni
                from pxr import Gf, Sdf, Usd, UsdGeom

                local_ns = {
                    "omni": omni,
                    "carb": carb,
                    "Usd": Usd,
                    "UsdGeom": UsdGeom,
                    "Sdf": Sdf,
                    "Gf": Gf,
                    "__file__": file_path,
                }
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
