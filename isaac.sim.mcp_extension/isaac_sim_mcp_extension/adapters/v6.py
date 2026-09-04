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

"""Isaac Sim 6.0.0 adapter implementation (PhysX + Newton)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .base import IsaacAdapterBase, collect_prims, drop_stale_bytecode, spherical_to_cartesian
from .transforms import read_transform, set_transform
from .units import limit_units, normalize_limit
from .version import version_string

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


class IsaacAdapterV6(IsaacAdapterBase):
    """Adapter for Isaac Sim 6.0.0 — backend-neutral (PhysX + Newton)."""

    def __init__(self) -> None:
        super().__init__()
        # The active engine is deliberately NOT captured here — see _engine.
        try:
            from isaacsim.core.version import get_version

            # 6.0 returns an 8-tuple, not a string — see adapters/version.py.
            self._isaacsim_version = version_string(get_version())
        except Exception:
            self._isaacsim_version = "unknown"
        # Articulation cache keyed by prim_path. Tensor-backed Articulations
        # bind to the current omni.physics.tensors SimulationView; that view
        # is destroyed and recreated on every timeline stop→play cycle, so the
        # cache is cleared on STOP. See _on_timeline_stop.
        self._articulations: Dict[str, Any] = {}
        # Sensor wrappers keyed by prim_path. Replicator annotators fill with
        # data on every render tick — discarding and recreating the wrapper
        # on each capture call (the 5.x pattern) means every call sees a
        # freshly-registered annotator with no accumulated frames, so
        # `get_data()` returns None. Long-lived wrappers let kit's normal
        # update tick populate the annotator between MCP calls.
        self._camera_sensors: Dict[str, Any] = {}
        self._lidar_sensors: Dict[str, Any] = {}
        # Pending Replicator render request, so repeated captures on an empty
        # sensor do not queue one task per call. See _request_render_frame.
        self._render_request = None
        self._timeline_stop_subscription = None
        try:
            import carb.eventdispatcher
            import omni.timeline

            def _on_timeline_stop(_event):
                self._articulations.clear()
                # Sensor wrappers hold annotator subscriptions and a render
                # product; release them on stop so a fresh play cycle
                # re-registers cleanly. Dropping the dict entry is not enough --
                # the subscriptions keep the wrapper, and the wrapper keeps its
                # prim, so the camera then could not be deleted and its render
                # product kept rendering. See base.release_sensor.
                self.release_all_sensors()

            self._timeline_stop_subscription = carb.eventdispatcher.get_eventdispatcher().observe_event(
                event_name=omni.timeline.GLOBAL_EVENT_STOP,
                on_event=_on_timeline_stop,
                observer_name="isaac_sim_mcp.v6.cache_reset_on_stop",
            )
        except Exception:
            pass

    @property
    def engine(self) -> str:
        """Public form of `_engine`, which the base declares and handlers ask.

        Kept as a thin alias: `_engine` has a dozen callers inside this adapter
        and its docstring carries the boot-order evidence for why it must stay
        a live read.
        """
        return self._engine

    def strands_first_rtx_camera(self) -> bool:
        """6.0 cannot remove the first RTX camera of a session (#20)."""
        return True

    @property
    def _engine(self) -> str:
        """Active physics backend: "physx" | "newton" | "remotesim" | "unknown".

        Read live on every access — never cached at construction time. Under the
        Newton kit the engine is still reported as the `physx` default while this
        extension is starting up: `isaacsim.physics.newton` registers the Newton
        backend later in the boot sequence. Measured on Isaac Sim 6.0.1 with
        isaac-sim.newton.sh:

            [3.978s] ext: isaac.sim.mcp_extension   <- adapter constructed here
            [6.649s] ext: isaacsim.physics.newton   <- engine becomes "newton"

        A value captured in __init__ therefore reports "physx" for the entire
        session under Newton, which is wrong in get_simulation_state and would
        silently mis-route any future backend-specific branch.
        """
        try:
            from isaacsim.core.simulation_manager import SimulationManager

            return SimulationManager.get_active_physics_engine()
        except Exception:
            return "unknown"

    # ── Scene ──────────────────────────────────────────────

    def get_stage(self) -> "Usd.Stage":
        import omni.usd

        return omni.usd.get_context().get_stage()

    def get_assets_root_path(self) -> str:
        from isaacsim.storage.native import get_assets_root_path

        return get_assets_root_path()

    def discover_environments(self) -> Dict[str, Dict[str, str]]:
        # Identical to V5 — uses omni.client, no Isaac Sim physics deps.
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
        from isaacsim.core.experimental.utils.stage import add_reference_to_stage

        add_reference_to_stage(env_path, prim_path)

    # ── Prims ──────────────────────────────────────────────

    def create_prim(self, prim_path: str, prim_type: str = "Xform", **kwargs) -> "Usd.Prim":
        from isaacsim.core.experimental.utils.stage import define_prim

        return define_prim(prim_path, type_name=prim_type)

    def delete_prim(self, prim_path: str) -> bool:
        import omni.kit.commands

        # A live sensor keeps its prim alive and re-creates it after a delete;
        # see prepare_prim_for_delete.
        self.prepare_prim_for_delete(prim_path)
        omni.kit.commands.execute("DeletePrims", paths=[prim_path])
        return True

    def add_reference_to_stage(self, usd_path: str, prim_path: str) -> "Usd.Prim":
        from isaacsim.core.experimental.utils.stage import add_reference_to_stage

        return add_reference_to_stage(usd_path, prim_path)

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

    def _simulated_position(self, prim_path: str) -> Optional[List[float]]:
        """World position from the physics view, or None if it cannot be read.

        Newton writes simulated transforms to Fabric and never back to USD, so a
        USD read reports the spawn pose forever: measured on 6.0.1, a body
        genuinely falling at -9.81 m/s still read z=20.0 through
        GetLocalTransformation, at every point during play. The physics view has
        the truth (19.54 while USD said 20.0), so rigid bodies are read from
        there on that engine.

        PhysX is left on the USD path deliberately: it writes back, and the USD
        read carries the prim's own local transform rather than a world pose,
        which is what the rest of this API reports.
        """
        try:
            from isaacsim.core.experimental.prims import RigidPrim

            positions, _ = RigidPrim(prim_path).get_world_poses()
            array = positions.numpy() if hasattr(positions, "numpy") else positions
            return [float(array[0][0]), float(array[0][1]), float(array[0][2])]
        except Exception:
            # Not a rigid body, physics not initialised, or the view is not
            # ready — the USD value is the best available answer.
            return None

    def get_prim_transform(self, prim_path: str) -> Dict[str, Any]:
        from pxr import UsdGeom

        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
        transform = read_transform(UsdGeom.Xformable(prim))
        if self._engine == "newton":
            # Newton writes simulated poses to Fabric, not to USD, so the USD
            # xform keeps reading the *spawn* pose no matter how far the body
            # has moved. Reporting that unlabelled is the same silent wrong
            # answer as the joint-read echo: measured on 6.0.1, a sphere resting
            # on the ground still read z=2.0 from USD.
            simulated, served = self._try_articulation(lambda: self._simulated_position(prim_path))
            if served and simulated is not None:
                # The Fabric pose is a WORLD position, so it belongs in
                # position_world. Writing it over position (which was
                # parent-relative on every other runtime) is what made one field
                # carry two frames depending on engine and prim type — #39.
                transform["position_world"] = simulated
                transform["position_world_source"] = "physics"
                transform.pop("position_world_warning", None)
                # position_world is now measured, but position_local still came
                # from USD -- the spawn pose, because Newton never writes back
                # to it. Replacing only the world value leaves the two fields
                # disagreeing about when they were taken, with nothing saying
                # so: the failure branch below carries a warning, and this, the
                # branch that actually serves data, carried none. Deriving a
                # local value from the measured world pose would need the
                # parent transform and would silently invent precision the USD
                # xform does not have, so label it instead.
                transform["position_local_warning"] = (
                    "position_world is measured from physics, but position_local is the authored USD pose "
                    "— Newton keeps simulated poses in Fabric and never writes them back, so for a body "
                    "that has moved this is its spawn pose. Use position_world, or get_physics_state."
                )
            elif self._prim_is_rigid_body(prim):
                # Only rigid bodies move under physics; for everything else USD
                # is the authority and a tag would be noise.
                transform["position_warning"] = (
                    "Newton keeps simulated poses in Fabric, and this position could not be read from "
                    "physics — it is the authored USD pose, which is the spawn pose for a body that has "
                    "been simulated. Both position_local and position_world derive from it, so both are "
                    "stale. Step the simulation and retry, or read the body through get_physics_state."
                )
        return transform

    @staticmethod
    def _prim_is_rigid_body(prim) -> bool:
        try:
            from pxr import UsdPhysics

            return bool(prim.HasAPI(UsdPhysics.RigidBodyAPI))
        except Exception:
            return False

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
        # Identical to V5 — pure pxr/UsdGeom math.
        from pxr import Usd, UsdGeom

        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
        prim_type = prim.GetTypeName()
        xformable = UsdGeom.Xformable(prim)
        local_transform = xformable.GetLocalTransformation()
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
            else:
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
            else:
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
        world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        translation = world_transform.ExtractTranslation()
        pos = [float(translation[0]), float(translation[1]), float(translation[2])]
        half = [d / 2.0 for d in dims]
        bbox_min = [pos[0] - half[0], pos[1] - half[1], pos[2] - half[2]]
        bbox_max = [pos[0] + half[0], pos[1] + half[1], pos[2] + half[2]]
        return dims, (bbox_min, bbox_max)

    # ── Robots ─────────────────────────────────────────────

    def create_xform_prim(self, prim_path: str) -> Any:
        from isaacsim.core.experimental.prims import XformPrim

        return XformPrim(paths=[prim_path])

    def create_articulation(self, prim_path: str, name: str) -> Any:
        from isaacsim.core.experimental.prims import Articulation

        return Articulation(paths=[prim_path])

    def _new_articulation(self, prim_path: str) -> Any:
        from isaacsim.core.experimental.prims import Articulation

        cached = self._articulations.get(prim_path)
        if cached is not None:
            return cached
        art = Articulation(paths=[prim_path])
        self._articulations[prim_path] = art
        return art

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

        # The walk is a few hundred directory listings over three levels. Run
        # each level concurrently: the calls are network round-trips against the
        # asset server, so they are latency bound, not CPU bound. Sequentially
        # they cost ~45 s on a cold omni.client cache on 6.0.1 — and kit's main
        # loop is blocked for the whole of it, so the app is frozen. Ordering is
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

    def get_robot_joint_info(self, prim_path: str) -> Dict[str, Any]:
        import traceback

        from pxr import Usd, UsdPhysics

        joint_names: List[str] = []
        num_dof = 0
        try:
            self._ensure_physics_world()
            art = self._new_articulation(prim_path)
            joint_names = list(art.dof_names) if art.dof_names else []
            num_dof = int(art.num_dofs) if art.num_dofs else 0
        except Exception as e:
            print(f"v6.get_robot_joint_info: tensor API failed for {prim_path}: {e}")
            traceback.print_exc()

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
        return {"joint_names": joint_names, "num_dof": num_dof, "joint_limits": joint_limits}

    def set_joint_positions(
        self,
        prim_path: str,
        positions: Sequence[float],
        joint_indices: Optional[List[int]] = None,
    ) -> None:
        import warp as wp

        def _apply():
            self._ensure_physics_world()
            art = self._new_articulation(prim_path)
            positions_arr = wp.array(np.asarray([list(positions)], dtype=np.float32), dtype=wp.float32)
            if joint_indices is not None:
                idx_arr = wp.array(np.asarray(joint_indices, dtype=np.int32), dtype=wp.int32)
                art.set_dof_position_targets(positions_arr, indices=idx_arr)
            else:
                art.set_dof_position_targets(positions_arr)
            return True

        _result, applied = self._try_articulation(_apply)
        # Record which one landed -- see the V5 note. A drive target does not
        # reach the solver until physics initializes again, and on Newton that
        # is the difference between a command and a no-op.
        self._note_joint_command_source(
            self.JOINT_COMMAND_ARTICULATION if applied else self.JOINT_COMMAND_DRIVE_TARGETS
        )
        if applied:
            return
        # USD-drive fallback (sim stopped / articulation not yet initialised)
        self._set_joint_drive_targets(prim_path, positions, joint_indices)

    def _set_joint_drive_targets(
        self,
        prim_path: str,
        positions: Sequence[float],
        joint_indices: Optional[List[int]] = None,
    ) -> None:
        # Identical to V5 — pure pxr.UsdPhysics.
        from pxr import Usd, UsdPhysics

        stage = self.get_stage()
        root_prim = stage.GetPrimAtPath(prim_path)
        if not root_prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
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
                drive.GetTargetPositionAttr().Set(float(value * 100.0))

    def _get_joint_names(self, prim_path: str) -> List[str]:
        def _names():
            self._ensure_physics_world()
            art = self._new_articulation(prim_path)
            return list(art.dof_names) if art.dof_names else None

        names, served = self._try_articulation(_names)
        if served and names:
            return names
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
        def _read():
            self._ensure_physics_world()
            art = self._new_articulation(prim_path)
            positions = art.get_dof_positions()
            if positions is None:
                raise RuntimeError("articulation returned no dof positions")
            # batched (1, num_dofs) wp.array → flat list
            arr = positions.numpy() if hasattr(positions, "numpy") else np.asarray(positions)
            return arr.reshape(-1).tolist()

        values, served = self._try_articulation(_read)
        if served and values is not None:
            self._note_joint_source(self.JOINT_SOURCE_PHYSICS)
            return values
        # USD fallback identical to V5: authored drive targets, which echo the
        # last set_joint_positions call. Tagged so a command cannot pass for a
        # measurement.
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
        from pxr import Usd, UsdPhysics

        self._ensure_physics_world()
        stage = self.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found: {prim_path}")
        joint_names = self._get_joint_names(prim_path)
        current_pos_list = self.get_joint_positions(prim_path)

        runtime_targets: List[float] = []
        try:
            art = self._new_articulation(prim_path)
            targets = art.get_dof_position_targets()
            if targets is not None:
                arr = targets.numpy() if hasattr(targets, "numpy") else np.asarray(targets)
                runtime_targets = arr.reshape(-1).tolist()
        except Exception:
            pass

        joints_info = []
        for desc in Usd.PrimRange(prim):
            if desc.IsA(UsdPhysics.RevoluteJoint) or desc.IsA(UsdPhysics.PrismaticJoint):
                joint_data: Dict[str, Any] = {"name": desc.GetName()}
                if desc.IsA(UsdPhysics.RevoluteJoint):
                    joint_data["type"] = "revolute"
                    joint_api = UsdPhysics.RevoluteJoint(desc)
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
                jname = desc.GetName()
                if jname in joint_names:
                    idx = joint_names.index(jname)
                    if idx < len(current_pos_list):
                        joint_data["actual_position"] = current_pos_list[idx]
                    if idx < len(runtime_targets):
                        joint_data["target_position"] = float(runtime_targets[idx])
                    if joint_data.get("target_position") is not None and "actual_position" in joint_data:
                        joint_data["position_error"] = joint_data["target_position"] - joint_data["actual_position"]
                joints_info.append(joint_data)

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

    def _ensure_physics_world(self) -> None:
        """Initialise SimulationManager (idempotent under both PhysX and Newton).

        Cleans stale PhysicsScene references first — the SimulationManager
        retains Python wrappers around scenes that may have been deleted via
        clear_scene, and calling setup_simulation/initialize_physics against
        them raises "Accessed invalid expired 'PhysicsScene' prim".
        """
        from isaacsim.core.simulation_manager import SimulationManager

        # Do nothing until the stage exists. setup_simulation() dereferences the
        # USD stage in native code, and Kit starts accepting MCP commands before
        # it has created one — measured on 6.0.1: the socket opens at [4.0s] and
        # the stage appears 2.86s later. A command landing in that window kills
        # the entire process:
        #
        #     [Fatal] [omni.usd] attempted member lookup on NULL TfWeakPtr<UsdStage>
        #
        # That is a native abort, not a Python exception, so it cannot be caught
        # — it has to be prevented. Reproduced 3/3 with any early execute_script,
        # including one whose body was just `print('hi')`, because this runs
        # before the submitted code does.
        # get_stage() can also raise while omni.usd is still coming up, so treat
        # "no stage" and "cannot ask yet" identically.
        try:
            if self.get_stage() is None:
                return
        except Exception:
            return
        try:
            SimulationManager._cleanup_stale_physics_scenes()
        except Exception:
            pass
        self._guard_newton_unsupported_geometry()
        # Keep whatever rate is already set. This runs from roughly nine call
        # sites — every step, joint read and physics-state query — and passing
        # a fixed dt reset the manager on each one. Measured on 6.0.1:
        # set_physics_dt(1/240) took effect, then a single get_physics_state
        # put it back to 1/60 with nothing said. set_physics_params tells the
        # caller to set the rate through execute_script precisely because no
        # adapter implements time_step, so this silently undid the documented
        # workaround.
        dt = 1.0 / 60.0
        try:
            current = SimulationManager.get_physics_dt()
            if current and float(current) > 0:
                dt = float(current)
        except Exception:
            pass  # no rate to preserve yet, or the manager cannot answer
        SimulationManager.setup_simulation(dt=dt)
        SimulationManager.initialize_physics()

    # Newton builds its model through SolverMuJoCo, whose geom_type_mapping has
    # no entry for GeoType.CONE (9) — see solver_mujoco.py add_geoms(). Kit
    # catches the resulting KeyError, logs "[Newton] Initialization failed:
    # np.int32(9)", and latches NewtonStage._init_failed = True. That latch is
    # permanent: initialize_newton() returns early forever after, so every
    # later physics call dies with "Failed to create simulation view with
    # backend 'newton'" and NOTHING recovers it — verified that deleting the
    # cone, clear_scene, and rebuilding the PhysicsScene all still fail. Only a
    # Kit restart clears it.
    #
    # Measured on 6.0.1-rc.7: cone + articulation bricks the session, while a
    # cone alone, a cylinder + articulation, and cone + articulation under
    # PhysX are all fine. Refusing before initialize_physics() keeps the latch
    # from ever being set, which is the difference between one bad tool call
    # and a dead simulator.
    NEWTON_UNSUPPORTED_TYPES = ("Cone",)

    # Newton's model builder also refuses a non-plane shape whose size is zero
    # ("Only plane shapes are allowed to have a size of zero"), and that failure
    # latches _init_failed exactly like the cone one does — same permanent kill,
    # same restart-only recovery. Found by the edge suite, which creates a
    # size=0 Cube: every later check reported a dead simulator.
    NEWTON_SIZE_ATTRS = {
        "Cube": ("size",),
        "Sphere": ("radius",),
        "Cylinder": ("radius", "height"),
        "Cone": ("radius", "height"),
        "Capsule": ("radius", "height"),
    }

    def _newton_zero_sized(self, prim) -> bool:
        """True when this prim is a non-plane shape collapsed to zero size."""
        attrs = self.NEWTON_SIZE_ATTRS.get(str(prim.GetTypeName()))
        if not attrs:
            return False
        for name in attrs:
            try:
                attr = prim.GetAttribute(name)
                if attr and attr.HasAuthoredValue() and float(attr.Get()) == 0.0:
                    return True
            except Exception:
                continue
        # A non-zero shape scaled flat reaches the solver the same way.
        try:
            scale = prim.GetAttribute("xformOp:scale")
            value = scale.Get() if scale else None
            if value is not None and any(float(c) == 0.0 for c in value):
                return True
        except Exception:
            pass
        return False

    def _newton_unsupported_geometry(self) -> list:
        """(path, reason) for prims that would brick Newton once an articulation exists."""
        try:
            stage = self.get_stage()
        except Exception:
            return []
        if stage is None:
            return []
        blockers, has_articulation = [], False
        try:
            from pxr import UsdPhysics

            articulation_api = getattr(UsdPhysics, "ArticulationRootAPI", None)
            for prim in stage.Traverse():
                if prim.GetTypeName() in self.NEWTON_UNSUPPORTED_TYPES:
                    blockers.append((str(prim.GetPath()), "cone geometry"))
                elif self._newton_zero_sized(prim):
                    blockers.append((str(prim.GetPath()), "zero size"))
                elif not has_articulation and self._is_articulation(prim, articulation_api):
                    has_articulation = True
        except Exception:
            return []
        return blockers if (blockers and has_articulation) else []

    @staticmethod
    def _is_articulation(prim, articulation_api) -> bool:
        """Articulation test that survives a missing/renamed schema binding.

        HasAPI() is the fast path; the applied-schema names are the fallback so
        one AttributeError cannot quietly switch the cone guard off and let the
        session get bricked instead.
        """
        if articulation_api is not None:
            try:
                return bool(prim.HasAPI(articulation_api))
            except Exception:
                pass
        try:
            return any("ArticulationRootAPI" in str(name) for name in prim.GetAppliedSchemas())
        except Exception:
            return False

    def _guard_newton_unsupported_geometry(self) -> None:
        """Refuse to initialise Newton physics on a stage that would latch it dead."""
        if self._engine != "newton":
            return
        blockers = self._newton_unsupported_geometry()
        if not blockers:
            return
        shown = ", ".join(f"{path} ({reason})" for path, reason in blockers[:5])
        if len(blockers) > 5:
            shown += " …"
        raise RuntimeError(
            "Newton cannot simulate this geometry together with an articulated robot: "
            f"{shown}. Its MuJoCo solver has no cone shape, and rejects any non-plane "
            "shape whose size is zero. Initialising anyway would permanently disable "
            "physics for this Isaac Sim session (only a restart recovers it), so the "
            "command was refused. Delete or resize the offending prim(s) — replace a "
            "cone with Cylinder/Capsule/Sphere/Cube, give a zero-sized shape a real "
            "size — or run this scene on the PhysX engine, which accepts both."
        )

    def _refresh_stale_physics_view(self) -> bool:
        """Rebuild the physics view after an articulation call found it stale.

        The tensor view enumerates articulations when it is built, and Kit only
        rebuilds it from the timeline STOP callback. The MCP debug loop is
        step-only and never stops, so adding a prim after the view exists — or
        clearing and rebuilding the scene — leaves reads and commands pointing
        at a view that does not contain the robot. Measured at HEAD on 6.0.1
        PhysX: set_joint_positions, create a prim, step, then read, and the read
        fell through to the USD drive targets and reported the commanded
        -0.4000 back as a measurement.

        initialize_physics() builds the views itself on 6.0 (unlike 5.1, which
        needs the warmup event), but it early-returns unless _warmup_needed is
        set — the flag Kit otherwise only sets on STOP.

        Refuses while the timeline is live: driving start_simulation() under a
        running scene is what aborted the GPU pipeline earlier in this project.
        """
        try:
            import omni.timeline

            if omni.timeline.get_timeline_interface().is_playing():
                return False
            from isaacsim.core.simulation_manager import SimulationManager
        except Exception:
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
            SimulationManager._warmup_needed = True
            SimulationManager.initialize_physics()
            return SimulationManager.get_physics_sim_view() is not None
        except Exception as exc:
            print(f"_refresh_stale_physics_view: could not rebuild the physics view ({exc})")
            return False

    def _try_articulation(self, operation):
        """Run an articulation operation, healing a stale physics view once.

        Returns (result, True) when it ran, (None, False) otherwise, so callers
        keep their USD fallbacks for the genuinely-unavailable case.
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

    def _newton_step_dt(self) -> float:
        """Seconds per stepped frame, from the PhysicsScene, defaulting to 1/60."""
        try:
            scene_path = self._find_physics_scene()
            if scene_path:
                attr = self.get_stage().GetPrimAtPath(scene_path).GetAttribute("physxScene:timeStepsPerSecond")
                rate = attr.Get() if attr else None
                if rate:
                    return 1.0 / float(rate)
        except Exception:
            pass
        return 1.0 / 60.0

    def _newton_step_direct(self, num_steps: int) -> bool:
        """Advance Newton by exactly num_steps frames, without pumping the app.

        NewtonStage.step_sim(dt) runs the solver directly and bumps sim_time and
        simulation_step_count by exactly one frame per call. It was missed when
        the pumped path was written: the APIs tried then were the PhysX-side
        ones (SimulationManager.step, SimulationView.step, physx.update_
        simulation), all of which leave Newton frozen, and the conclusion drawn
        was that no direct solver step exists. It does.

        Measured on 6.0.1-rc.7, 30 calls at dt=1/60 from a paused timeline:
        sim_time 0.05000 -> 0.55000 and step count 3 -> 33, both exact, with the
        timeline never playing and the body falling as expected. The pumped path
        advances ~30.6 frames for the same request, because a pump runs a real
        app frame whose physics substepping does not land on the boundary.

        step_sim() only runs the solver while NewtonStage.playing is set, which
        the timeline event otherwise drives, so it is set for the duration and
        restored afterwards. Fabric holds Newton's simulated transforms, so
        update_fabric() has to run before any read.

        Returns False when this build cannot be stepped this way, so step()
        falls back to the pump rather than silently doing nothing.
        """
        try:
            import isaacsim.physics.newton as newton_ext

            newton_stage = newton_ext.acquire_stage()
        except Exception:
            return False
        if newton_stage is None:
            return False
        if not getattr(newton_stage, "initialized", False) or getattr(newton_stage, "_init_failed", False):
            return False
        step_sim = getattr(newton_stage, "step_sim", None)
        if not callable(step_sim):
            return False

        dt = self._newton_step_dt()
        was_playing = getattr(newton_stage, "playing", False)
        try:
            newton_stage.playing = True
            for _ in range(num_steps):
                step_sim(dt)
        except Exception as exc:
            print(f"_newton_step_direct: falling back to the pump ({exc})")
            return False
        finally:
            try:
                newton_stage.playing = was_playing
            except Exception:
                pass
        try:
            newton_stage.update_fabric()
        except Exception as exc:
            print(f"_newton_step_direct: update_fabric failed ({exc})")
        return True

    def _newton_model_bodies(self):
        """(NewtonStage, set of body paths in its model) or (None, None)."""
        try:
            import isaacsim.physics.newton as newton_ext

            newton_stage = newton_ext.acquire_stage()
        except Exception:
            return None, None
        if newton_stage is None:
            return None, None
        model = getattr(newton_stage, "model", None)
        if model is None:
            return newton_stage, None
        try:
            return newton_stage, {str(path) for path in (getattr(model, "body_label", []) or [])}
        except Exception:
            return newton_stage, None

    def _refresh_newton_model_if_stale(self) -> bool:
        """Rebuild Newton's model when it no longer matches the stage.

        Newton builds its model once and rebuilds it from the timeline STOP
        event. A step-only debug loop never stops, so after a clear_scene the
        model keeps the *deleted* prims and never learns about the new ones —
        and Newton keeps stepping that phantom scene. Measured on 6.0.1-rc.7
        through the tools: clear_scene from a paused timeline, create a sphere
        at z=2, step 60, and it reports z=2.0 with zero velocity while
        model.body_label still reads ['/World/Ball'] for a prim that no longer
        exists. sim_time and the step counter advance throughout, so nothing
        looks wrong. The same sphere dropped after a stop_simulation — which
        does fire the rebuild — lands correctly at z=0.149.

        Only the stopped/paused case is handled: rebuilding underneath a running
        scene is the kind of thing that cost this project a GPU-level PhysX
        abort, and while playing Kit maintains the model itself.
        """
        if self._engine != "newton":
            return False
        try:
            import omni.timeline

            if omni.timeline.get_timeline_interface().is_playing():
                return False
        except Exception:
            return False

        newton_stage, model_bodies = self._newton_model_bodies()
        if newton_stage is None:
            return False
        # Kit has not built a model yet, or a previous build failed and latched
        # (see the cone guard) — leave both alone.
        if not getattr(newton_stage, "initialized", False) or getattr(newton_stage, "_init_failed", False):
            return False

        try:
            from pxr import UsdPhysics

            stage_bodies = {
                str(prim.GetPath()) for prim in self.get_stage().Traverse() if prim.HasAPI(UsdPhysics.RigidBodyAPI)
            }
        except Exception:
            return False

        if model_bodies is not None and model_bodies == stage_bodies:
            return False
        # Same refusal as _ensure_physics_world: this rebuild calls
        # initialize_newton() directly, so without the guard a cone or a
        # zero-sized shape latches physics dead here instead — measured on
        # 6.0.1-rc.7, where a size=0 Cube killed the simulator through this
        # path while the guard on the other path never saw it.
        self._guard_newton_unsupported_geometry()
        try:
            newton_stage.initialized = False
            newton_stage.initialize_newton(None)
        except Exception as exc:
            print(f"_refresh_newton_model_if_stale: rebuild failed ({exc})")
            return False
        return not getattr(newton_stage, "_init_failed", False)

    def _arm_reset_point(self) -> None:
        """Give stop_simulation something to restore to, without running the sim.

        PhysX records its restore point on a Play, and it records the state as
        of the moment play() is called. V6 advances physics with
        SimulationManager.step(), which never plays, so a run driven purely by
        step_simulation had no restore point and stop_simulation silently did
        nothing — a cube stepped down from z=2 stayed on the ground.

        Play cannot simply be called and observed: timeline transitions are
        tick-driven, and a handler may not pump kit's event loop (see step), so
        is_playing() is still False on the next line. Queueing play() and
        pause() together sidesteps that — by the time the next tick lands the
        timeline is paused, and no frame ever runs free. Measured on 6.0.1: a
        cube left at z=50.0 was still at exactly 50.0 afterwards, physics step
        count unchanged, and a subsequent stop_simulation restored it to 50.0
        from 48.73.

        Deliberately NOT the agent's job: asking the caller to play then pause
        costs a network round trip between the two, during which the sim runs
        free — measured at ~1.4s of fall — which is exactly the imprecision
        step_simulation exists to remove.

        Queueing alone is not enough: the transition is tick-driven, so it lands
        a tick *after* this returns, and a stop_simulation issued promptly finds
        no restore point and silently keeps the stepped pose. Measured on 6.0.1:
        a cube stepped from z=2.0 stayed at z=-3.32 through stop when the two
        calls were back to back, and reset correctly with any delay between
        them -- so the bug hid behind human-speed interaction and only bites the
        agent-speed debug loop this tool exists to serve. One app.update() lands
        the transition before returning, which is exactly the piece of the V5
        step this adapter otherwise avoids.

        That single pump is deliberately *not* the pumped stepping V5 does: see
        step(), which keeps SimulationManager.step for the physics so no frame
        ever runs free. Verified on 6.0.1/physx -- pump-to-arm reproduces V6's
        exact stepped result (z=-3.322, identical to no arming) while V5-style
        pumped stepping lands at z=-2.987, and the reset then works with no
        delay, 3/3. Re-check under Newton before assuming it holds there.

        Only arms while the timeline is stopped, so it re-arms once per run and
        never disturbs a genuine Play already in progress.
        """
        try:
            import omni.timeline

            timeline = omni.timeline.get_timeline_interface()
            if timeline.is_stopped():
                timeline.play()
                timeline.pause()
                try:
                    import omni.kit.app

                    omni.kit.app.get_app().update()
                except Exception:
                    # Pumping from inside the dispatch coroutine is the hazard
                    # step() documents. It did not reproduce here on
                    # 6.0.1/physx, but if it ever does, losing the pump costs
                    # only the reset -- degrading to the old tick-late
                    # behaviour -- and must not break stepping itself.
                    pass
        except Exception:
            # Best effort: failing to arm costs the ability to reset, but must
            # never stop the caller from stepping.
            pass

    def create_world(self, **kwargs) -> Any:
        """V6 exposes SimulationManager (a class-level singleton) where V5 returned World()."""
        from isaacsim.core.simulation_manager import SimulationManager

        return SimulationManager

    def create_simulation_context(self, **kwargs) -> Any:
        from isaacsim.core.simulation_manager import SimulationManager

        return SimulationManager

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
        has_rb = prim.HasAPI(UsdPhysics.RigidBodyAPI)
        result["has_rigid_body"] = has_rb
        if has_rb:
            rb = UsdPhysics.RigidBodyAPI(prim)
            kinematic_attr = rb.GetKinematicEnabledAttr()
            result["is_kinematic"] = kinematic_attr.Get() if kinematic_attr else False
        has_mass = prim.HasAPI(UsdPhysics.MassAPI)
        if has_mass:
            mass_api = UsdPhysics.MassAPI(prim)
            mass_attr = mass_api.GetMassAttr()
            result["mass"] = mass_attr.Get() if mass_attr else None
        result["collision_enabled"] = prim.HasAPI(UsdPhysics.CollisionAPI)

        if has_rb:
            lin_vel = [0.0, 0.0, 0.0]
            ang_vel = [0.0, 0.0, 0.0]
            # Pre-seeded zeros made "no physics view", "view invalidated" and
            # "genuinely at rest" indistinguishable: a moving body read as
            # stationary with nothing said. V5 reports velocity_warning for its
            # own version of this (PhysX write-back disabled); say so here too
            # rather than passing an unmeasured zero off as a measurement.
            measured = False
            try:
                from isaacsim.core.simulation_manager import SimulationManager

                view = SimulationManager.get_physics_simulation_view()
                if view is not None:
                    rb_view = view.create_rigid_body_view([prim_path])
                    vels = rb_view.get_velocities()
                    arr = vels.numpy() if hasattr(vels, "numpy") else np.asarray(vels)
                    if arr.size >= 6:
                        flat = arr.reshape(-1)[:6]
                        lin_vel = [float(flat[0]), float(flat[1]), float(flat[2])]
                        ang_vel = [float(flat[3]), float(flat[4]), float(flat[5])]
                        measured = True
            except Exception:
                pass
            result["linear_velocity"] = lin_vel
            result["angular_velocity"] = ang_vel
            if not measured:
                result["velocity_warning"] = (
                    "The physics tensor view could not serve this read, so the velocities above "
                    "are placeholder zeros, not a measurement -- a moving body looks identical to "
                    "one at rest. Step the simulation at least once, and check get_isaac_logs."
                )

        result["contacts"] = []
        return result

    # ── Sensors ────────────────────────────────────────────

    def _request_render_frame(self) -> bool:
        """Ask Replicator to render one frame, without starting the timeline.

        RTX sensor data comes from Replicator's orchestrator, which by default
        only captures while the timeline plays (/omni/replicator/captureOnPlay).
        The documented debug loop is step-only and never plays, so on 6.0.1 the
        orchestrator sat at STOPPED and every camera returned an empty frame
        forever.

        Two obvious remedies are wrong here:

          * orchestrator.run() starts the timeline. Measured on 6.0.1: from a
            stopped timeline it left playing=True, which turns the sim loose and
            destroys the frame-exact stepping step_simulation exists to provide.
          * The synchronous orchestrator.step() is refused outright by
            Replicator from inside kit — "Synchronous call to `step` can only be
            performed in a standalone workflow ... Please use the async function
            `step_async`" — which matches the rule that handlers must not pump
            kit's event loop.

        So schedule step_async and return immediately. It runs on kit's loop
        once this handler is done, captures a single frame with pause_timeline
        set, and leaves the timeline exactly as it found it. Measured: timeline
        stayed stopped, orchestrator reached STEPPED, the next capture returned
        a real image, and the kit log recorded no reentry errors.

        The frame is therefore ready on the *next* call, not this one — the
        caller is told to retry rather than being handed a blank image.
        """
        try:
            import asyncio

            import omni.replicator.core as rep

            pending = self._render_request
            if pending is not None and not pending.done():
                return True
            self._render_request = asyncio.ensure_future(rep.orchestrator.step_async(pause_timeline=True))
            return True
        except Exception:
            return False

    def _apply_sensor_schema(self, prim_path: str) -> None:
        """Make an already-present prim acceptable to the RTX sensor wrappers.

        No-op when the prim does not exist yet — the wrapper will create it with
        the right schema itself. See create_camera for why this is needed.
        """
        try:
            prim = self.get_stage().GetPrimAtPath(prim_path)
            if prim and prim.IsValid() and "OmniSensorAPI" not in prim.GetAppliedSchemas():
                prim.ApplyAPI("OmniSensorAPI")
        except Exception:
            # Leave it to the sensor wrapper to raise a meaningful error.
            pass

    def create_camera(self, prim_path: str, resolution: Tuple[int, int] = (1280, 720), **kwargs) -> Any:
        # 6.0 RtxCamera takes a single `path: str` — the 5.x batched
        # (`prim_paths=[...], resolutions=[...]`) signature was removed.
        # Also stand up the CameraSensor runtime + RGB annotator now so kit's
        # background render ticks start filling the annotator immediately;
        # later capture_image calls read accumulated frames from the cache.
        from isaacsim.sensors.experimental.rtx import CameraSensor, RtxCamera

        # RtxCamera adopts an existing prim rather than redefining it, and it
        # does not apply OmniSensorAPI to one it did not create. Pointing
        # create_camera at a path that already holds a plain UsdGeom.Camera —
        # which imported USD scenes routinely ship — therefore failed with
        # "Prim at <path> does not have the 'OmniSensorAPI' schema", while the
        # same call on a fresh path succeeded. Reproduced on 6.0.1: fresh path
        # OK, plain Camera at the path FAIL, existing RTX camera OK.
        #
        # Apply the schema first so an existing camera prim reaches RtxCamera in
        # the same shape a newly created one would. A prim that does not exist
        # yet needs nothing: RtxCamera creates it correctly.
        self._apply_sensor_schema(prim_path)
        camera = RtxCamera(path=prim_path)
        # CameraSensor expects (height, width). Adapter callers historically
        # pass (width, height) — translate so the cached resolution is sane.
        h, w = (resolution[1], resolution[0]) if len(resolution) == 2 else (720, 1280)
        self._camera_sensors[prim_path] = CameraSensor(path=prim_path, resolution=(h, w), annotators=["rgb"])
        return camera

    def capture_camera_image(self, prim_path: str) -> np.ndarray:
        # Reuse the wrapper cached by create_camera. Building a fresh
        # CameraSensor on every call re-registers the annotator with the
        # render pipeline and discards any frames produced since the prim
        # was created, so `get_data` returns None — that was the root cause
        # of the "empty data" symptom. With a long-lived wrapper, kit's
        # background update tick fills the annotator between MCP commands
        # and get_data returns the latest rendered frame.
        from isaacsim.sensors.experimental.rtx import CameraSensor

        sensor = self._camera_sensors.get(prim_path)
        if sensor is None:
            sensor = CameraSensor(path=prim_path, resolution=(720, 1280), annotators=["rgb"])
            self._camera_sensors[prim_path] = sensor
        data, _info = sensor.get_data("rgb")
        if data is None:
            # Nothing rendered yet. Ask Replicator for a frame so the next call
            # succeeds, instead of leaving cameras permanently blank in the
            # step-only debug loop.
            self._request_render_frame()
            return np.zeros((0,), dtype=np.uint8)
        return data.numpy() if hasattr(data, "numpy") else np.asarray(data)

    # 6.0's Lidar constructor takes only a path; presets are schema
    # attributes applied afterwards, so the bare constructor yields a generic
    # sensor. Measured on 6.0.1: config="Example_Rotary" and no config both
    # produce model=LidarCore, channels=128.
    SUPPORTS_LIDAR_CONFIG = False

    def create_lidar(self, prim_path: str, config: Optional[str] = None, **kwargs) -> Any:
        # 6.0 Lidar takes a single `path: str`. Hardware preset (formerly the
        # `config` arg) is now set through schema attributes after creation;
        # the bare constructor produces a generic OmniLidar prim. As with
        # create_camera, also cache a LidarSensor wrapper so its annotator
        # starts producing data on kit's regular render tick.
        from isaacsim.sensors.experimental.rtx import Lidar, LidarSensor

        lidar = Lidar(path=prim_path)
        self._lidar_sensors[prim_path] = LidarSensor(path=prim_path, annotators=["generic-model-output"])
        return lidar

    def get_lidar_point_cloud(self, prim_path: str) -> np.ndarray:
        # 6.0 LidarSensor uses the unified "generic-model-output" annotator;
        # the 5.x `RtxSensorCpu+IsaacComputeRTXLidarPointCloud` chain is gone.
        # See `capture_camera_image` for the caching rationale.
        from isaacsim.sensors.experimental.rtx import LidarSensor, parse_generic_model_output_data

        sensor = self._lidar_sensors.get(prim_path)
        if sensor is None:
            sensor = LidarSensor(path=prim_path, annotators=["generic-model-output"])
            self._lidar_sensors[prim_path] = sensor
        data, info = sensor.get_data("generic-model-output")
        array = None
        if data is not None:
            array = data.numpy() if hasattr(data, "numpy") else np.asarray(data)
        # LidarSensor signals "nothing rendered yet" with an empty array rather
        # than None (measured on 6.0.1: shape (0,), info {}), unlike CameraSensor
        # which returns None — so testing only for None missed the empty case.
        #
        # Deliberately no _request_render_frame() here. A single Replicator frame
        # fills a camera but not a lidar: measured on 6.0.1 with the orchestrator
        # at STEPPED and the request completed, the sensor was still empty, and
        # only play_simulation produced data. Requesting one would just make the
        # caller retry forever.
        if array is None or getattr(array, "size", 0) == 0:
            return np.zeros((0, 3), dtype=np.float32)

        # The "generic-model-output" annotator returns a packed GenericModelOutput
        # struct, not points: a uint8 buffer whose first four bytes are the magic
        # 0x4E474D4F ("OMGN"). Returning it raw meant callers received bytes and
        # the handler reported len(buffer) as a point count — 19,353,864 for one
        # frame on 6.0.1, which is the byte length.
        #
        # 5.x had a point-cloud annotator that needed no decoding; 6.0 replaced it
        # with this unified buffer plus parse_generic_model_output_data, and the
        # port kept the new annotator without adopting the decode.
        gmo = parse_generic_model_output_data(data)
        count = int(getattr(gmo, "numElements", 0) or 0)
        if count <= 0:
            return np.zeros((0, 3), dtype=np.float32)
        x = np.asarray(gmo.x)[:count]
        y = np.asarray(gmo.y)[:count]
        z = np.asarray(gmo.z)[:count]
        # x/y/z are only Cartesian when the sensor says so. The shipped rotary
        # configs declare SPHERICAL, and returning those raw handed callers
        # azimuth/elevation degrees under a "meters" label: a 2 m wall 3 m ahead
        # came back spanning +-18.4 (its subtended angle) with a "z" of 3.0 (the
        # range). Read the convention off the prim rather than assuming either.
        if self._lidar_elements_are_spherical(prim_path):
            rows = spherical_to_cartesian(x, y, z)
            x = [r[0] for r in rows]
            y = [r[1] for r in rows]
            z = [r[2] for r in rows]
        return np.stack([x, y, z], axis=-1).astype(np.float32)

    def _lidar_elements_are_spherical(self, prim_path: str) -> bool:
        """Read `omni:sensor:Core:elementsCoordsType` off the lidar prim.

        Defaults to True when the attribute is missing or unreadable: every
        shipped rotary config measured on 6.0.1 is SPHERICAL, so assuming
        Cartesian would silently restore the wrong-units bug.
        """
        try:
            prim = self.get_stage().GetPrimAtPath(prim_path)
            attr = prim.GetAttribute("omni:sensor:Core:elementsCoordsType")
            if attr and attr.IsValid():
                value = attr.Get()
                if value is not None:
                    return str(value).upper() == "SPHERICAL"
        except Exception:
            pass
        return True

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

    # ── Assets ─────────────────────────────────────────────

    def import_urdf(self, urdf_path: str, prim_path: str = "/World/robot", **kwargs) -> Any:
        # 6.0 splits URDF import into two steps:
        #   1) URDFImporter.import_urdf() converts the .urdf to a .usd on disk
        #      (the `dest_path` kwarg from 5.x is gone — output dir is chosen
        #      via `usd_path` on the config, defaulting to the URDF's directory)
        #   2) the caller references that .usd into the live stage
        import os
        import tempfile

        if not os.path.isfile(urdf_path):
            raise FileNotFoundError(f"URDF file not found: {urdf_path}")
        from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig

        usd_out_dir = kwargs.pop("usd_path", None) or tempfile.mkdtemp(prefix="urdf_import_")
        config = URDFImporterConfig(urdf_path=urdf_path, usd_path=usd_out_dir, **kwargs)
        importer = URDFImporter(config)
        usd_path = importer.import_urdf()
        # Bring the generated USD into the live stage at the requested prim path
        return self.add_reference_to_stage(usd_path, prim_path)

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
        # spawn pose — it is what the Isaac UI Stop button does. Verified on
        # 6.0.1: a cube dropped from z=2 returns to exactly z=2 after this call.
        #
        # There used to be a SimulationManager.reset_simulation() here. That
        # method does not exist on 6.0.1 — the call raised
        # "type object 'SimulationManager' has no attribute 'reset_simulation'"
        # on every stop and a bare except swallowed it, so stop_simulation
        # reported success while doing nothing beyond the line above. Do not
        # reintroduce it without checking the API actually exists.
        omni.timeline.get_timeline_interface().stop()

    def step(
        self,
        num_steps: int = 1,
        observe_prims: Optional[List[str]] = None,
        observe_joints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        # SimulationManager.step pumps only the physics pipeline (no asyncio
        # event-loop reentry), which avoids the "Cannot enter into task" errors
        # that omni.kit.app.update() triggers when called from inside the MCP
        # dispatch coroutine on Kit 107 (Isaac Sim 6.0). SocketServer
        # ._dispatch_command documents this as a hard constraint on handlers.
        #
        # Do NOT drive the *stepping* with app.update() here, the way V5 does.
        # Two separate reasons, and only the second is fatal:
        #
        # 1. It changes the physics. Pumped stepping runs real frames at the
        #    app's cadence and cannot stop the timeline on an exact boundary,
        #    so the same 60-frame fall lands at z=-2.987 instead of the
        #    SimulationManager.step result of z=-3.322, and the timeline is
        #    still playing on return — free-running between MCP calls is the
        #    imprecision step_simulation exists to remove.
        # 2. It has been observed to flood the log with
        #     RuntimeError: Cannot enter into task <...> while another task
        #     <SocketServer._dispatch_command...execute_wrapper> is being executed
        # killing unrelated kit tasks mid-flight (property window, viewport,
        # USD cache listener, throttling, HTTP server) and invalidating the
        # physics tensor view, after which get_velocities/get_transforms fail
        # with "Simulation view object is invalidated".
        #
        # That flood did not reproduce on 6.0.1/physx when re-checked: 60
        # pumped updates from inside this coroutine logged no task errors and
        # left the tensor view valid, so the hazard is evidently state- or
        # backend-dependent rather than unconditional. Treat it as real but not
        # universal, and keep the exactness argument in (1) as the standing
        # reason. _arm_reset_point does pump exactly once, guarded, because a
        # tick-late restore point breaks stop_simulation outright.
        from isaacsim.core.simulation_manager import SimulationManager

        self._ensure_physics_world()
        self._arm_reset_point()

        # Newton is not driven by any direct solver step. Measured on 6.0.1
        # under isaac-sim.newton.sh, dropping a body from z=20 for 60 steps
        # where free fall predicts z=15.095:
        #
        #     SimulationManager.step      z=20.0000  vz=0.0000   no motion
        #     SimulationView.step(dt)     z=20.0000  vz=0.0000   no motion
        #     physx.update_simulation     z=20.0000  vz=0.0000   no motion
        #     pumped app.update()         z=14.8918  vz=-10.0063 runs
        #
        # so on Newton the app tick is the only thing that advances the solver,
        # and step_simulation silently froze the world without it. The pump is
        # about one step plus render jitter off exact, which is the accuracy
        # ceiling available there — reported as "approximate" rather than
        # implied to match PhysX. PhysX keeps SimulationManager.step, which is
        # frame-exact; pumping it instead changes its answers too (-2.987
        # against -3.322 over the same fall).
        approximate = self._engine == "newton"
        suspended_graphs = []
        rebuilt_model = False
        if approximate:
            import omni.kit.app
            import omni.timeline

            rebuilt_model = self._refresh_newton_model_if_stale()

            timeline = omni.timeline.get_timeline_interface()
            resume_paused = not timeline.is_playing()
            stepped_directly = False
            # Running the timeline evaluates Action Graphs, so a ScriptNode
            # controller re-commands the robot on every stepped frame and
            # silently discards the caller's set_joint_positions -- measured on
            # Newton as 30 ScriptNode ticks during a 30-frame step. PhysX never
            # needed this because SimulationManager.step pumps only the physics
            # pipeline. Suspending keeps the debug loop the same shape on both
            # engines: step on a frozen timeline with graphs quiet, play for the
            # graph-driven run.
            with self._graphs_suspended() as suspended:
                suspended_graphs = [str(path) for path in suspended] if suspended else []
                # Preferred: step the solver directly, which is frame-exact and
                # never runs an app frame. The pump below is the fallback for
                # builds without NewtonStage.step_sim.
                stepped_directly = self._newton_step_direct(num_steps)
                if not stepped_directly:
                    if resume_paused:
                        timeline.play()
                    try:
                        for _ in range(num_steps):
                            omni.kit.app.get_app().update()
                    finally:
                        if resume_paused:
                            # Pause, not stop: stop resets to the spawn pose and
                            # throws away the physics result being measured.
                            timeline.pause()
        else:
            SimulationManager.step(steps=num_steps)

        if rebuilt_model:
            # The rebuild itself leaves the tensor view usable, but the
            # play/pump/pause cycle above then invalidates it, so the next
            # articulation read degrades to the drive-target fallback and
            # reports the caller's own command back (caught by position_source
            # during testing). Re-prime once so reads stay physics-backed.
            try:
                self._ensure_physics_world()
            except Exception as exc:
                print(f"step: could not re-prime physics after a Newton model rebuild ({exc})")

        result: Dict[str, Any] = {"stepped": num_steps}
        if rebuilt_model:
            result["newton_model_rebuilt"] = True
        if suspended_graphs:
            result["graphs_suspended"] = suspended_graphs
        if approximate:
            if stepped_directly:
                result["stepping"] = "exact"
            else:
                result["stepping"] = "approximate"
                result["stepping_note"] = (
                    "This build has no NewtonStage.step_sim, so the frames were advanced by pumping "
                    "the app tick, which lands about one step past the requested count. Newton is "
                    "still deterministic — repeated runs of the same scene agree bit for bit."
                )

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
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    try:
                        from isaacsim.core.simulation_manager import SimulationManager

                        view = SimulationManager.get_physics_simulation_view()
                        rb_view = view.create_rigid_body_view([path]) if view is not None else None
                        if rb_view is not None:
                            transforms = rb_view.get_transforms()
                            arr = transforms.numpy() if hasattr(transforms, "numpy") else np.asarray(transforms)
                            if arr.size >= 3:
                                flat = arr.reshape(-1)
                                state["position"] = [float(flat[0]), float(flat[1]), float(flat[2])]
                        else:
                            transform = self.get_prim_transform(path)
                            state["position"] = transform.get("position_world") or transform.get(
                                "position_local", [0, 0, 0]
                            )
                    except Exception:
                        transform = self.get_prim_transform(path)
                        state["position"] = transform.get("position_world") or transform.get(
                            "position_local", [0, 0, 0]
                        )
                else:
                    transform = self.get_prim_transform(path)
                    # World, to match the physics branch above: PhysX and the
                    # tensor view both report world positions, so falling back
                    # to the parent-relative one silently changed the frame of
                    # this field depending on whether the physics read
                    # succeeded -- in the field most used to measure motion.
                    state["position"] = transform.get("position_world") or transform.get("position_local", [0, 0, 0])
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    try:
                        ps = self.get_physics_state(path)
                        state["linear_velocity"] = ps.get("linear_velocity", [0, 0, 0])
                        state["angular_velocity"] = ps.get("angular_velocity", [0, 0, 0])
                    except Exception:
                        pass
                prim_states.append(state)
            result["prim_states"] = prim_states

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
        from pxr import UsdPhysics

        timeline = omni.timeline.get_timeline_interface()
        is_playing = timeline.is_playing()
        is_stopped = timeline.is_stopped()
        if is_playing:
            timeline_state = "playing"
        elif is_stopped:
            timeline_state = "stopped"
        else:
            timeline_state = "paused"

        # Report the physics clock, not the timeline clock. V6 advances physics
        # with SimulationManager.step(), which never runs the timeline (handlers
        # may not pump kit's event loop — see step), so timeline.get_current_time()
        # stays at 0.0 for the entire step-only debug loop no matter how far the
        # simulation has run. SimulationManager.get_simulation_time() tracks every
        # physics step and resets to 0 on stop, which is the "time since this run
        # began" that callers expect. Measured on 6.0.1: +1.0000s per step(60),
        # and back to ~0 after stop.
        try:
            from isaacsim.core.simulation_manager import SimulationManager

            current_time = float(SimulationManager.get_simulation_time())
        except Exception:
            current_time = timeline.get_current_time()
        stage = self.get_stage()
        physics_dt = 1.0 / 60.0
        # Kit accepts MCP commands before it has created a stage — measured on
        # 6.0.1 the socket opens 2.86s ahead of it, and 5.1.0 behaves the same.
        # Traversing None there raised "'NoneType' object has no attribute
        # 'Traverse'", turning a routine status query into an opaque error during
        # startup. The timeline state is still knowable, so report that and fall
        # back to the default physics_dt.
        prims = stage.Traverse() if stage is not None else []
        for prim in prims:
            try:
                if prim.IsA(UsdPhysics.Scene):
                    time_step_attr = prim.GetAttribute("physxScene:timeStepsPerSecond")
                    if time_step_attr and time_step_attr.Get():
                        steps_per_sec = time_step_attr.Get()
                        if steps_per_sec > 0:
                            physics_dt = 1.0 / steps_per_sec
                    break
            except Exception:
                pass

        return {
            "timeline_state": timeline_state,
            "current_time": current_time,
            "physics_dt": physics_dt,
            "engine": self._engine,
            "isaacsim_version": self._isaacsim_version,
        }

    def execute_script(self, code: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        import io
        import sys
        import traceback

        import carb
        import omni
        from pxr import Gf, Sdf, Usd, UsdGeom

        if cwd and cwd not in sys.path:
            sys.path.insert(0, cwd)

        local_ns = {"omni": omni, "carb": carb, "Usd": Usd, "UsdGeom": UsdGeom, "Sdf": Sdf, "Gf": Gf}

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

    _exec_namespaces: Dict[str, dict] = {}

    def reload_script(self, file_path: str, module_name: Optional[str] = None) -> Dict[str, Any]:
        import importlib
        import io
        import os
        import sys
        import traceback

        parent_dir = os.path.dirname(os.path.abspath(file_path))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        # Both branches below need this, not just the reload. Python's
        # FileFinder caches a directory listing, so a controller written moments
        # ago is invisible to import_module even with its directory on sys.path
        # -- measured on 5.1.0: ModuleNotFoundError before invalidate_caches(),
        # imported fine straight after.
        importlib.invalidate_caches()

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

        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = captured_out = io.StringIO()
        sys.stderr = captured_err = io.StringIO()
        try:
            if module_name:
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
