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

from .base import IsaacAdapterBase, collect_prims, drop_stale_bytecode
from .transforms import read_transform, set_transform
from .units import limit_units, normalize_limit

if TYPE_CHECKING:
    from pxr import Usd


def _recompile_scriptnodes_for_file(abs_path: str) -> list:
    """Recompile every Action-Graph ScriptNode whose scriptPath matches abs_path.

    Returns the list of recompiled node paths (empty if none matched).
    """
    import os

    try:
        import omni.graph.core as og

        from ..handlers.graphs import force_recompile_scriptnode
    except Exception:
        return []

    recompiled = []
    try:
        graphs = og.get_all_graphs() if hasattr(og, "get_all_graphs") else []
    except Exception:
        graphs = []
    for graph in graphs:
        try:
            for node in graph.get_nodes():
                attr = node.get_attribute("inputs:scriptPath")
                if attr is None or not attr.is_valid():
                    continue
                val = attr.get()
                if val and os.path.abspath(str(val)) == abs_path:
                    force_recompile_scriptnode(graph, node)
                    recompiled.append(node.get_prim_path())
        except Exception:
            continue
    return recompiled


class IsaacAdapterV5(IsaacAdapterBase):
    """Adapter for Isaac Sim 5.1.0 (isaacsim.* namespace)."""

    def __init__(self) -> None:
        super().__init__()
        # Long-lived Camera wrappers keyed by prim_path, and the subset that has
        # been initialized. A Camera only fills its buffer on render ticks after
        # initialize(), so a wrapper rebuilt per call can never return a frame —
        # and initialize() must run exactly once per camera, since each call
        # creates a render product, attaches annotators and registers three
        # event subscriptions. See capture_camera_image.
        self._camera_sensors: Dict[str, Any] = {}
        self._initialized_cameras: set = set()
        # Lidars need the same treatment as cameras, and for the same reason:
        # the annotator must be attached before initialize() and survives only
        # as long as the wrapper does. See get_lidar_point_cloud.
        self._lidar_sensors: Dict[str, Any] = {}

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

        # A live sensor keeps its prim alive and re-creates it after a delete;
        # see prepare_prim_for_delete.
        self.prepare_prim_for_delete(prim_path)
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
                # Skip hidden directories. Every asset folder keeps a ".thumbs"
                # of "<name>.thumb.usd" previews, which otherwise registered as
                # environments named e.g. "grid_.thumbs" pointing at a
                # thumbnail: 8 of the 36 entries returned on 6.0.1 were these.
                if name.lstrip("/").startswith("."):
                    continue
                dir_path = root + base + name + "/"
                r2, files = omni.client.list(dir_path)
                if r2 != omni.client.Result.OK:
                    continue
                # Find USD files at this level
                for f in files:
                    if f.relative_path.endswith(".thumb.usd"):
                        continue  # preview image, not an environment
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
                    if subname.lstrip("/").startswith("."):
                        continue
                    r3, subfiles = omni.client.list(dir_path + subname + "/")
                    if r3 != omni.client.Result.OK:
                        continue
                    for sf in subfiles:
                        if sf.relative_path.endswith(".thumb.usd"):
                            continue
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

    def _refresh_stale_physics_view(self) -> bool:
        """Rebuild the physics view after an articulation read found it stale.

        The view is a process-level singleton that enumerates articulations when
        it is built, and Kit only ever invalidates it from `_on_stop` — a
        *timeline STOP event*. The MCP debug loop is step-only and never plays,
        so that event never fires: the view built for the first robot survives
        clear_scene, still points at the deleted prims, and never learns about
        articulations added later. SingleArticulation.initialize() then fails
        with "'NoneType' object has no attribute 'link_names'", which the read
        path swallows, so every joint read reports 0 DOF from the second robot
        of a session onward — permanently. Measured on 5.1: cycle 1 of
        clear -> physics -> robot reads 9 DOF, cycles 2-4 read 0, with the sim
        view object identical (same id) across all four.

        Two constraints learned the hard way, both by crashing the simulator:

        * This runs ONLY from the read path, after a read has already failed —
          never eagerly on asset creation. Rebuilding on every add_reference
          call killed Kit with "PhysX ABORT: cannot start GPU simulation
          because of previous CUDA errors! Error code 700" during the
          integration suite (43/43 passing without it, hard crash with it).
        * It refuses while the timeline is live. initialize_physics() drives
          start_simulation()/fetch_results(), and doing that underneath a
          running scene is what corrupts the GPU pipeline.

        Returns True when the view was actually rebuilt and the read is worth
        retrying.
        """
        import omni.timeline

        timeline = omni.timeline.get_timeline_interface()
        # Refuse only while the timeline is LIVE, not merely paused.
        # step_simulation leaves the timeline PAUSED, which is exactly where a
        # stale view gets discovered, so requiring is_stopped() meant the heal
        # never ran there. Measured on 5.1 with two robots: with the stricter
        # guard, deleting one left the survivor's reads and commands falling
        # through to the drive-target fallback (6/9 checks); allowing paused
        # restores them to physics-backed (8/9).
        if timeline.is_playing():
            return False
        try:
            from isaacsim.core.simulation_manager import SimulationManager
        except ImportError:
            return False
        try:
            for attr in ("_physics_sim_view", "_physics_sim_view__warp"):
                view = getattr(SimulationManager, attr, None)
                if view is not None:
                    try:
                        view.invalidate()
                    except Exception:
                        pass
                    setattr(SimulationManager, attr, None)
            SimulationManager._simulation_view_created = False
            # _create_simulation_view is subscribed to PHYSICS_WARMUP, and
            # initialize_physics() only dispatches that event while
            # _warmup_needed is set — normally by the STOP callback.
            SimulationManager._warmup_needed = True
            self._resync_physics_scene_cache()
            SimulationManager.initialize_physics()
            return True
        except Exception as exc:
            print(f"_refresh_stale_physics_view: could not rebuild the physics view ({exc})")
            return False

    def set_prim_transform(
        self,
        prim_path: str,
        position: Optional[Sequence[float]] = None,
        rotation: Optional[Sequence[float]] = None,
        scale: Optional[Sequence[float]] = None,
    ) -> None:
        from pxr import UsdGeom

        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
        xformable = UsdGeom.Xformable(prim)
        # Which op holds the rotation, and where it sits relative to scale,
        # decides whether a requested rotation replaces or compounds. See
        # adapters/transforms.py.
        set_transform(xformable, position=position, rotation=rotation, scale=scale)

    def get_prim_transform(self, prim_path: str) -> Dict[str, Any]:
        from pxr import UsdGeom

        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
        return read_transform(UsdGeom.Xformable(prim))

    def list_prims(
        self, root_path: str = "/", prim_type: Optional[str] = None, recursive: bool = False
    ) -> List[Dict[str, str]]:
        stage = self.get_stage()
        root = stage.GetPrimAtPath(root_path)
        return collect_prims(root, prim_type=prim_type, recursive=recursive)

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

        # The walk is ~150 directory listings deep in three levels. Run each
        # level concurrently: the calls are network round-trips against the
        # asset server, so they are latency bound, not CPU bound, and doing them
        # one at a time costs ~28 s on a cold omni.client cache — during which
        # kit's main loop is blocked and the whole app is frozen. Ordering is
        # preserved by mapping over the input list, so the key-preference rules
        # below behave exactly as they did sequentially.
        def _list_dir(path: str):
            try:
                res, entries = omni.client.list(path)
                return entries if res == omni.client.Result.OK else []
            except Exception:
                return []

        def _map(paths):
            if len(paths) < 2:
                return [_list_dir(p) for p in paths]
            try:
                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=min(16, len(paths))) as pool:
                    return list(pool.map(_list_dir, paths))
            except Exception:
                # Any threading problem: fall back to the sequential walk.
                return [_list_dir(p) for p in paths]

        mfr_names = [m.relative_path.rstrip("/") for m in manufacturers]
        mfr_models = _map([robots_base + n + "/" for n in mfr_names])

        # Flatten to (manufacturer, model) pairs, then list every model dir at once.
        # Skip hidden directories: every manufacturer keeps a ".thumbs" folder of
        # "<model>.thumb.usd" preview files, which otherwise register as a robot
        # named ".thumbs" pointing at a thumbnail.
        pairs = [
            (mfr_name, model_entry.relative_path.rstrip("/"))
            for mfr_name, models in zip(mfr_names, mfr_models)
            for model_entry in models
            if not model_entry.relative_path.lstrip("/").startswith(".")
        ]
        model_files = _map([f"{robots_base}{mfr}/{model}/" for mfr, model in pairs])

        for (mfr_name, model_name), files in zip(pairs, model_files):
            for file_entry in files:
                fname = file_entry.relative_path
                if not (fname.endswith(".usd") or fname.endswith(".usda")):
                    continue
                if fname.endswith(".thumb.usd"):
                    continue  # preview image, not a robot
                asset_rel = f"/Isaac/Robots/{mfr_name}/{model_name}/{fname}"

                # Use lowercase model name as key, prefer shorter/simpler names
                key = model_name.lower().replace(" ", "_")
                if key in discovered:
                    # Keep the simpler filename (shorter name wins). Rewrite the
                    # whole record, not just the path: two manufacturers can ship
                    # the same model directory name, and updating the path alone
                    # left entries describing one vendor while pointing at
                    # another's asset.
                    if len(fname) < len(discovered[key]["asset_path"].split("/")[-1]):
                        discovered[key] = {
                            "asset_path": asset_rel,
                            "description": f"{mfr_name} {model_name}",
                            "manufacturer": mfr_name,
                        }
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

        def _info():
            art = SingleArticulation(prim_path=prim_path)
            art.initialize()
            return (list(art.dof_names) if art.dof_names else [], art.num_dof if art.num_dof else 0)

        info, ok = self._try_articulation(_info)
        if ok and info:
            joint_names, num_dof = info

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
                    limit_entry["lower"] = normalize_limit(lo, "revolute")
                    limit_entry["upper"] = normalize_limit(hi, "revolute")
                    limit_entry["units"] = limit_units("revolute")
                    break
                if desc.IsA(UsdPhysics.PrismaticJoint):
                    pris = UsdPhysics.PrismaticJoint(desc)
                    lo = pris.GetLowerLimitAttr().Get()
                    hi = pris.GetUpperLimitAttr().Get()
                    limit_entry["type"] = "prismatic"
                    limit_entry["lower"] = normalize_limit(lo, "prismatic")
                    limit_entry["upper"] = normalize_limit(hi, "prismatic")
                    limit_entry["units"] = limit_units("prismatic")
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

        def _apply():
            art = SingleArticulation(prim_path=prim_path)
            art.initialize()
            action = ArticulationAction(
                joint_positions=np.array(positions),
                joint_indices=np.array(joint_indices) if joint_indices else None,
            )
            art.get_articulation_controller().apply_action(action)
            return True

        _result, applied = self._try_articulation(_apply)
        # Record which one landed. A drive target is authored into USD and does
        # not reach the solver until physics initializes again, so the caller
        # has to be able to tell it from a live articulation command -- the
        # handler reported the same success for both.
        self._note_joint_command_source(
            self.JOINT_COMMAND_ARTICULATION if applied else self.JOINT_COMMAND_DRIVE_TARGETS
        )
        if not applied:
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

        self._ensure_physics_world()

        def _names():
            art = SingleArticulation(prim_path=prim_path)
            art.initialize()
            return list(art.dof_names) if art.dof_names else None

        names_from_physics, ok = self._try_articulation(_names)
        if ok and names_from_physics:
            return names_from_physics

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

    def _try_articulation(self, operation):
        """Run an articulation operation, healing a stale physics view once.

        Every articulation entry point hits the same wall: the view is rebuilt
        only by Kit's timeline STOP callback, which a step-only session never
        fires, so anything created after the view was built is invisible to it.
        Reads degrade to USD fallbacks (see get_joint_positions), but a *command*
        has nowhere to degrade to — measured on 5.1, commanding joints without a
        prior read left the arm at 0.000 after 120 steps against a target of
        -0.400, because the robot was not in the simulation at all.

        Returns (result, True) when the operation ran, (None, False) otherwise,
        so callers keep their own USD fallbacks for the genuinely-unavailable
        case. The refresh declines while the timeline is live, so this is inert
        during a play run.
        """
        try:
            return operation(), True
        except Exception:
            pass
        if self._refresh_stale_physics_view():
            try:
                return operation(), True
            except Exception:
                pass
        return None, False

    def _articulation_positions(self, prim_path: str) -> Optional[List[float]]:
        """Joint positions from the physics view, or None when it cannot serve them."""
        from isaacsim.core.prims import SingleArticulation

        try:
            art = SingleArticulation(prim_path=prim_path)
            art.initialize()
            positions = art.get_joint_positions()
            if positions is not None:
                return positions.tolist()
        except Exception:
            return None
        return None

    # NOTE: get_joint_positions drives the retry itself so it can tag
    # position_source on the fallback; the helper covers everything else.

    def get_joint_positions(self, prim_path: str) -> List[float]:

        # Ensure physics is initialized so SingleArticulation.initialize() works
        self._ensure_physics_world()

        positions = self._articulation_positions(prim_path)
        if positions is None and self._refresh_stale_physics_view():
            # The physics view outlived the prims it was built against; it has
            # been rebuilt, so the same read is worth exactly one retry.
            positions = self._articulation_positions(prim_path)
        if positions is not None:
            self._note_joint_source(self.JOINT_SOURCE_PHYSICS)
            return positions

        # Fallback: read drive target positions from USD
        # WARNING: these are authored targets, not actual physics positions —
        # they echo whatever set_joint_positions last wrote. Tagged so the
        # caller is told, rather than mistaking a command for a measurement.
        self._note_joint_source(self.JOINT_SOURCE_DRIVE_TARGETS)
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

        self._ensure_physics_world()
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

                # USD keeps revolute limits in degrees; positions below are in
                # radians. See adapters/units.py.
                joint_type = joint_data["type"]
                joint_data["lower_limit"] = normalize_limit(lower_attr.Get() if lower_attr else None, joint_type)
                joint_data["upper_limit"] = normalize_limit(upper_attr.Get() if upper_attr else None, joint_type)
                joint_data["limit_units"] = limit_units(joint_type)

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

        # Warn about joints with zero stiffness (broken drive config)
        warnings = []
        for j in joints_info:
            stiff = j.get("stiffness")
            damp = j.get("damping")
            if stiff is not None and stiff == 0 and (damp is None or damp == 0):
                warnings.append(
                    f"Joint '{j['name']}' has stiffness=0 and damping=0 — "
                    f"its drive is effectively disabled and will not respond to position targets."
                )

        result: Dict[str, Any] = {
            "prim_path": prim_path,
            "joint_count": len(joints_info),
            "joints": joints_info,
        }
        if warnings:
            result["warnings"] = warnings
        return result

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
        # Reuse a scene that already exists rather than adding a second one:
        # two PhysicsScenes break physics state reads. See _find_physics_scene.
        existing = self._find_physics_scene(preferred_path=scene_path)
        if existing is not None:
            scene_path = existing
        else:
            omni.kit.commands.execute("CreatePrim", prim_path=scene_path, prim_type="PhysicsScene")
        if gravity is not None:
            # Without this the argument was accepted and discarded — see
            # _apply_gravity.
            self._apply_gravity(scene_path, gravity)
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

        # Velocities come from the physics:* attributes, which PhysX writes back
        # every simulated frame.
        #
        # This used to read omni.physx get_rigidbody_transformation(), but that
        # call only returns {position, rotation, ret_val} — there is no velocity
        # in the payload, so `.get("linear_velocity", (0, 0, 0))` silently
        # returned zeros on every call and a moving body was indistinguishable
        # from one at rest. Verified against a cube falling at 15 m/s: the physx
        # call had no velocity key while physics:velocity read [0, 0, -15.042].
        #
        # Units: physics:velocity is m/s. physics:angularVelocity is deg/s in USD,
        # converted to rad/s here so angular values match the radians this API
        # uses everywhere else (joint positions, limits).
        if has_rb:
            result["linear_velocity"] = [0.0, 0.0, 0.0]
            result["angular_velocity"] = [0.0, 0.0, 0.0]
            try:
                lin = prim.GetAttribute("physics:velocity")
                if lin and lin.Get() is not None:
                    result["linear_velocity"] = [float(v) for v in lin.Get()]
                ang = prim.GetAttribute("physics:angularVelocity")
                if ang and ang.Get() is not None:
                    result["angular_velocity"] = [float(np.radians(v)) for v in ang.Get()]
            except Exception:
                pass
            # PhysX only writes these attributes back while /physics/updateToUsd
            # and /physics/updateVelocitiesToUsd are enabled (both default on).
            # If either is off, the reads above stay at zero — say so rather than
            # reporting a moving body as stationary, which is the silent failure
            # this code path used to have.
            try:
                import carb

                settings = carb.settings.get_settings()
                if settings.get("/physics/updateToUsd") is False or (
                    settings.get("/physics/updateVelocitiesToUsd") is False
                ):
                    result["velocity_warning"] = (
                        "physics USD write-back is disabled (/physics/updateToUsd or "
                        "/physics/updateVelocitiesToUsd is false), so velocities read as zero "
                        "regardless of actual motion."
                    )
            except Exception:
                pass

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

        camera = Camera(prim_path=prim_path, resolution=resolution, **kwargs)
        # Keep the wrapper so capture_camera_image reads this camera — created
        # with the caller's resolution — instead of building a throwaway one.
        self._camera_sensors[prim_path] = camera
        self._initialized_cameras.discard(prim_path)
        return camera

    def capture_camera_image(self, prim_path: str) -> np.ndarray:
        """Return the latest RGBA frame, or an empty array if none has rendered.

        This used to build `Camera(prim_path=prim_path)` on every call and read
        get_rgba() immediately, which could never return an image:

          * A Camera only fills its buffer on render ticks *after* initialize(),
            and this never called it.
          * A wrapper created inside the call has had no tick to render into, so
            its first read is always empty — and the next call discarded it and
            started over.
          * Rebuilding without the resolution also dropped the one requested at
            create_camera, so captures came back at the 128x128 Camera default.

        Verified on Isaac Sim 5.1.0: capture returned an empty array on every
        call with the timeline stopped *and* playing, while a wrapper kept alive
        and initialized returned a real (128, 128, 4) frame on the next call.

        initialize() runs at most once per camera. Calling it per capture — the
        first version of this fix — left kit alive but unresponsive: the
        integration suite went from 7s to not finishing in 240s. Each call
        creates a render product, attaches annotators and registers three event
        subscriptions, so repeating it per request accumulates work the renderer
        then carries every frame.
        """
        from isaacsim.sensors.camera import Camera

        camera = self._camera_sensors.get(prim_path)
        if camera is None:
            camera = Camera(prim_path=prim_path)
            self._camera_sensors[prim_path] = camera
        if prim_path not in self._initialized_cameras:
            try:
                camera.initialize()
            except Exception:
                # A camera whose render product is not ready yet reads as
                # "no frame", not as a failed capture.
                pass
            self._initialized_cameras.add(prim_path)
        data = camera.get_rgba()
        if data is None:
            return np.zeros((0,), dtype=np.uint8)
        return data

    # 5.1 exposes the decoded point cloud through this annotator; 6.0 replaced
    # it with a packed generic-model-output buffer (see v6.get_lidar_point_cloud).
    # 5.1's LidarRtx takes config_file_name and applies the preset.
    SUPPORTS_LIDAR_CONFIG = True

    LIDAR_POINT_CLOUD_ANNOTATOR = "IsaacExtractRTXSensorPointCloudNoAccumulator"

    def _lidar_sensor(self, prim_path: str, config: Optional[str] = None, **kwargs) -> Any:
        """Return a cached LidarRtx with its point-cloud annotator live.

        The annotator must be attached *before* initialize(): calling
        initialize() first leaves the sensor with zero annotators and every
        frame empty, measured on 5.1.0.
        """
        from isaacsim.sensors.rtx import LidarRtx

        sensor = self._lidar_sensors.get(prim_path)
        if sensor is None:
            # 5.1's LidarRtx takes config_file_name; passing `config` lands in
            # **kwargs and collides with the kit command's own argument, raising
            # "got multiple values for keyword argument 'config'".
            sensor = LidarRtx(prim_path=prim_path, config_file_name=config or "Example_Rotary", **kwargs)
            sensor.attach_annotator(self.LIDAR_POINT_CLOUD_ANNOTATOR)
            sensor.initialize()
            self._lidar_sensors[prim_path] = sensor
        return sensor

    def create_lidar(self, prim_path: str, config: Optional[str] = None, **kwargs) -> Any:
        return self._lidar_sensor(prim_path, config=config, **kwargs)

    def get_lidar_point_cloud(self, prim_path: str) -> np.ndarray:
        # LidarRtx has no get_point_cloud() on 5.1 — the old call raised
        # "'LidarRtx' object has no attribute 'get_point_cloud'" on every read.
        # Rebuilding the wrapper per call was equally fatal: a fresh one carries
        # no annotator, so it could never return a frame.
        sensor = self._lidar_sensor(prim_path)
        frame = sensor.get_current_frame() or {}
        payload = frame.get(self.LIDAR_POINT_CLOUD_ANNOTATOR)
        data = payload.get("data") if isinstance(payload, dict) else None
        if data is None:
            return np.zeros((0, 3), dtype=np.float32)
        points = np.asarray(data)
        # This annotator only yields on frames where a sweep completes, so an
        # empty read is "not this frame", not "the lidar saw nothing" — the
        # handler turns it into a retry message.
        if points.size == 0 or points.ndim != 2 or points.shape[1] != 3:
            return np.zeros((0, 3), dtype=np.float32)
        return points.astype(np.float32)

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
        # URDFImportRobot needs the *parsed* robot object; without urdf_robot it
        # calls import_robot(None) and returns (False, None). And its dest_path
        # is a USD *file* path to write (it runs Usd.Stage.CreateNew on it), not
        # a prim path — passing "/World/robot" made it try to author a stage at
        # that filename. Both mistakes failed silently: the command's False was
        # returned unchecked, so the handler reported a successful import while
        # nothing whatsoever landed on the stage. Verified on 5.1 against three
        # different URDFs (fr3, lula_franka_gen, cobotta_pro_900): status
        # success, requested prim absent, zero articulations on the stage.
        #
        # dest_path="" imports in-memory onto the open stage and returns the
        # prim path it chose (the robot's own name, e.g. "/fr3"), so the result
        # is moved to the requested prim_path and verified before returning.
        import os

        if not os.path.isfile(urdf_path):
            raise FileNotFoundError(f"URDF file not found: {urdf_path}")
        import omni.kit.commands

        _status, import_config = omni.kit.commands.execute("URDFCreateImportConfig")
        parsed, urdf_robot = omni.kit.commands.execute(
            "URDFParseFile", urdf_path=urdf_path, import_config=import_config
        )
        if not parsed or urdf_robot is None:
            raise RuntimeError(f"URDF parse failed for {urdf_path}")

        imported, imported_path = omni.kit.commands.execute(
            "URDFImportRobot",
            urdf_path=urdf_path,
            urdf_robot=urdf_robot,
            import_config=import_config,
            dest_path="",
        )
        if not imported or not imported_path:
            raise RuntimeError(f"URDF import failed for {urdf_path} (importer returned no prim)")

        return self._relocate_imported_prim(imported_path, prim_path)

    def _relocate_imported_prim(self, imported_path: str, prim_path: str) -> str:
        """Move a freshly imported robot to the requested path; report where it really is."""
        stage = self.get_stage()
        if not prim_path or imported_path == prim_path:
            return imported_path
        try:
            import omni.kit.commands

            omni.kit.commands.execute("MovePrim", path_from=imported_path, path_to=prim_path)
        except Exception:
            pass
        # Never claim a path that is not on the stage — that is the bug this
        # whole method exists to stop.
        if stage.GetPrimAtPath(prim_path):
            return prim_path
        return imported_path

    # ── Simulation ─────────────────────────────────────────

    def play(self) -> None:
        import omni.timeline

        self._ensure_physics_world()
        omni.timeline.get_timeline_interface().play()

    def pause(self) -> None:
        import omni.timeline

        omni.timeline.get_timeline_interface().pause()

    def stop(self) -> None:
        import omni.timeline

        # timeline.stop() already restores rigid bodies / articulations to their
        # spawn pose — it is what the Isaac UI Stop button does. Verified on 5.1:
        # a cube dropped from z=2 to z=0.1 returns to exactly z=2 after this call.
        #
        # Do NOT add World.reset() here. It re-starts the timeline (verified:
        # stop_simulation then reported "playing" with the time advancing), and
        # the restart lands on a later frame, so stopping again immediately does
        # not help. A stop that leaves the sim running makes step_simulation
        # refuse to run and breaks the step-only debug loop.
        omni.timeline.get_timeline_interface().stop()

    def step(
        self, num_steps: int = 1, observe_prims: Optional[List[str]] = None, observe_joints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        # Advance physics by exactly num_steps frames on a frozen timeline, then
        # freeze again, so the caller can inspect the result — the V6 contract,
        # where SimulationManager.step(steps=N) does this natively.
        #
        # Pumping omni.kit.app.update() alone (the old behaviour) does NOT
        # advance physics while the timeline is stopped: a cube left at z=2 was
        # still at z=2 with zero velocity after 70 "steps", so every observation
        # came back identical and the step-only debug loop could never simulate
        # anything. Physics only ticks while the timeline runs, so run it for the
        # requested frames and pause immediately afterwards.
        import omni.kit.app
        import omni.timeline

        self._ensure_physics_world()
        timeline = omni.timeline.get_timeline_interface()
        resume_paused = not timeline.is_playing()
        # Running the timeline also evaluates Action Graphs, so a ScriptNode
        # controller would re-command the robot on every stepped frame and
        # silently discard the caller's set_joint_positions. Suspend graphs for
        # the duration; play is the mode for driving them.
        with self._graphs_suspended() as suspended:
            if resume_paused:
                timeline.play()
            try:
                for _ in range(num_steps):
                    omni.kit.app.get_app().update()
            finally:
                if resume_paused:
                    # Pause (not stop): stop would reset everything to the spawn
                    # pose and discard exactly the physics result being measured.
                    timeline.pause()

        result: Dict[str, Any] = {"stepped": num_steps}
        if suspended:
            result["graphs_suspended"] = [str(p) for p in suspended]

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
                # Prefer PhysX runtime position for rigid bodies (always current)
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    try:
                        import omni.physx

                        physx = omni.physx.get_physx_interface()
                        rb_data = physx.get_rigidbody_transformation(path)
                        if rb_data and rb_data.get("ret_val", False):
                            pos = rb_data["position"]
                            state["position_world"] = [float(pos[0]), float(pos[1]), float(pos[2])]
                        else:
                            transform = self.get_prim_transform(path)
                            state["position_world"] = transform.get("position_world") or transform.get(
                                "position_local", [0, 0, 0]
                            )
                    except Exception:
                        transform = self.get_prim_transform(path)
                        state["position_world"] = transform.get("position_world") or transform.get(
                            "position_local", [0, 0, 0]
                        )
                else:
                    transform = self.get_prim_transform(path)
                    # World, to match the physics branch above: PhysX and the
                    # tensor view both report world positions, so falling back
                    # to the parent-relative one silently changed the frame of
                    # this field depending on whether the physics read
                    # succeeded -- in the field most used to measure motion.
                    state["position_world"] = transform.get("position_world") or transform.get(
                        "position_local", [0, 0, 0]
                    )
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
        # Kit accepts MCP commands before it has created a stage — measured on
        # 6.0.1 the socket opens 2.86s ahead of it, and 5.1.0 behaves the same.
        # Traversing None there raised "'NoneType' object has no attribute
        # 'Traverse'", turning a routine status query into an opaque error during
        # startup. The timeline state is still knowable, so report that and fall
        # back to the default physics_dt.
        prims = stage.Traverse() if stage is not None else []
        for prim in prims:
            if prim.IsA(UsdPhysics.Scene):
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
            self._ensure_physics_world()
            exec(code, local_ns)
            out = captured_out.getvalue()
            if out.strip():
                try:
                    from ..handlers.simulation import append_log

                    for line in out.splitlines():
                        append_log(f"[PRINT] {line}")
                except Exception:
                    pass
            return {
                "status": "success",
                "message": "Script executed successfully",
                "stdout": out,
                "stderr": captured_err.getvalue(),
            }
        except Exception as e:
            out = captured_out.getvalue()
            if out.strip():
                try:
                    from ..handlers.simulation import append_log

                    for line in out.splitlines():
                        append_log(f"[PRINT] {line}")
                except Exception:
                    pass
            return {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc(),
                "stdout": out,
                "stderr": captured_err.getvalue(),
            }
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr

    # Track exec() namespaces to clean up subscriptions on reload
    _exec_namespaces: Dict[str, dict] = {}

    def reload_script(self, file_path: str, module_name: Optional[str] = None) -> Dict[str, Any]:
        import importlib
        import io
        import os
        import sys

        # Auto-add parent directory to sys.path
        parent_dir = os.path.dirname(os.path.abspath(file_path))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        # Both branches below need this, not just the reload. Python's
        # FileFinder caches a directory listing, so a controller written moments
        # ago is invisible to import_module even with its directory on sys.path
        # -- measured on 5.1.0: ModuleNotFoundError before invalidate_caches(),
        # imported fine straight after.
        importlib.invalidate_caches()

        # Clean up previous exec() namespace for this file (unsubscribe orphaned callbacks)
        abs_path = os.path.abspath(file_path)

        # ScriptNode-aware reload: if any Action-Graph ScriptNode references this
        # file via inputs:scriptPath, force it to recompile (the standalone
        # re-exec below would not touch the running graph node).
        recompiled = _recompile_scriptnodes_for_file(abs_path)
        if recompiled:
            return {
                "status": "success",
                "message": f"Recompiled ScriptNode(s) referencing {os.path.basename(file_path)}",
                "recompiled_nodes": recompiled,
            }

        old_ns = self._exec_namespaces.get(abs_path)
        if old_ns:
            for key, val in old_ns.items():
                if hasattr(val, "unsubscribe"):
                    try:
                        val.unsubscribe()
                    except Exception:
                        pass

        # Capture stdout/stderr
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = captured_out = io.StringIO()
        sys.stderr = captured_err = io.StringIO()
        try:
            if module_name:
                # Reload existing module or import for first time
                if module_name in sys.modules:
                    # Drop the cached bytecode first: reload() alone re-ran the
                    # previous contents for a same-length edit and still
                    # reported success (issue #27).
                    existing = getattr(sys.modules[module_name], "__file__", None)
                    if existing:
                        drop_stale_bytecode(existing)
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
                self._ensure_physics_world()
                exec(code, local_ns)
                # Track namespace so we can clean up subscriptions on next reload
                self._exec_namespaces[abs_path] = local_ns
                msg = f"Script '{os.path.basename(file_path)}' executed successfully"

            out = captured_out.getvalue()
            if out.strip():
                try:
                    from ..handlers.simulation import append_log

                    for line in out.splitlines():
                        append_log(f"[PRINT] {line}")
                except Exception:
                    pass
            return {
                "status": "success",
                "message": msg,
                "stdout": out,
                "stderr": captured_err.getvalue(),
            }
        except Exception as e:
            out = captured_out.getvalue()
            if out.strip():
                try:
                    from ..handlers.simulation import append_log

                    for line in out.splitlines():
                        append_log(f"[PRINT] {line}")
                except Exception:
                    pass
            return {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc(),
                "stdout": out,
                "stderr": captured_err.getvalue(),
            }
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
