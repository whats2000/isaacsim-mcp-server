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

"""Scene management command handlers."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from ..adapters.base import IsaacAdapterBase

_discovered_envs: Optional[Dict[str, Dict[str, str]]] = None


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["scene.get_info"] = lambda **p: get_info(adapter, **p)
    registry["scene.create_physics"] = lambda **p: create_physics(adapter, **p)
    registry["scene.clear"] = lambda **p: clear(adapter, **p)
    registry["scene.list_prims"] = lambda **p: list_prims(adapter, **p)
    registry["scene.get_prim_info"] = lambda **p: get_prim_info(adapter, **p)
    registry["scene.list_environments"] = lambda **p: list_environments(adapter, **p)
    registry["scene.load_environment"] = lambda **p: load_environment(adapter, **p)


def get_info(adapter: IsaacAdapterBase) -> Dict[str, Any]:
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


def _find_collision_floor(stage, root: Optional[str] = None) -> Optional[str]:
    """Path of a collision-enabled ground plane, or None.

    Searches the whole stage by default; pass ``root`` to search only that
    subtree. #38 needs the scoped form: a ``/World/groundPlane`` left by an
    earlier create_physics_scene is not the loaded environment's floor, and on a
    dirty stage it can sit at a different height entirely.

    Deliberately narrow: a prim of type ``Plane`` carrying ``CollisionAPI``.
    That is what the shipped environments author (simple_warehouse ships
    ``GroundPlane/CollisionPlane``) and it cannot mistake scenery for a floor.

    The looser rule considered here — any collision prim whose bbox is wide and
    thin — also catches Mesh-authored floors, but a 3 x 1 x 0.05 m wall panel or
    a tabletop matches it just as well, and suppressing a floor the caller needs
    is a worse failure than the stacking this guards against. An environment
    whose floor is a Mesh therefore still stacks; that is recorded on #37.
    """
    from pxr import Usd, UsdPhysics

    try:
        if root is None:
            prims = stage.Traverse()
        else:
            root_prim = stage.GetPrimAtPath(root)
            if not root_prim or not root_prim.IsValid():
                return None
            prims = Usd.PrimRange(root_prim)
        for prim in prims:
            if prim.GetTypeName() != "Plane":
                continue
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                return str(prim.GetPath())
    except Exception:
        # A stage that cannot be walked must not fail the whole call; fall
        # through and create the plane, which is the pre-#37 behaviour.
        return None
    return None


def _prim_world_z(stage, prim_path: str) -> Optional[float]:
    """World-space Z of a prim's origin.

    The world transform, not the local one: _reference_conversion rotates and
    rescales Y-up / centimetre environments immediately before bounds are read,
    so a floor prim's authored translate is not its height on the stage.
    """
    from pxr import Usd, UsdGeom

    try:
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return None
        matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        return float(matrix.ExtractTranslation()[2])
    except Exception:
        return None


def create_physics(
    adapter: IsaacAdapterBase, gravity: Optional[Sequence[float]] = None, scene_name: str = "PhysicsScene"
) -> Dict[str, Any]:
    try:
        from pxr import UsdPhysics

        scene_path = adapter.create_physics_scene(gravity=gravity, scene_name=scene_name)
        # Ground plane with collision so objects don't fall through — but only
        # when the stage has no floor of its own. load_environment brings its
        # own collision floor, and adding a second one leaves two: in
        # simple_warehouse both happen to sit at z=0 so nothing looks wrong,
        # while on an environment whose floor is elsewhere the objects rest at
        # a height nothing on screen explains, and which plane wins is PhysX's
        # decision rather than the caller's.
        #
        # Creation also stays idempotent: create_prim raises "A prim already
        # exists at prim path" on a second call, and because the scene is
        # established first the tool would report failure for work it had just
        # completed — while naming groundPlane, which looks unrelated to the
        # caller's request. Re-establishing a scene on a dirty stage is normal.
        stage = adapter.get_stage()
        floor_path = "/World/groundPlane"
        existing_floor = _find_collision_floor(stage)
        ground_plane_created = False
        if existing_floor is not None:
            ground_plane = existing_floor
        else:
            ground_plane = floor_path
            # A groundPlane that exists without collision reaches here, because
            # a plane that holds nothing up is not a floor. Adopt it rather than
            # recreating it.
            if not stage.GetPrimAtPath(floor_path).IsValid():
                adapter.create_prim(floor_path, "Plane")
                ground_plane_created = True
            gp = stage.GetPrimAtPath(floor_path)
            if gp.IsValid() and not gp.HasAPI(UsdPhysics.CollisionAPI):
                UsdPhysics.CollisionAPI.Apply(gp)

        # Bring physics up NOW, while the stage still holds no articulation.
        #
        # PhysX corrupts its GPU pipeline if the simulation is first set up
        # with an articulation already on the stage and another is added
        # afterwards: the next start dies with "PhysX Internal CUDA error.
        # Simulation cannot continue! Error code 700", followed by one
        # "PhysX ABORT ... because of previous CUDA errors" per stepped frame.
        # The simulator keeps answering and step_simulation still reports
        # success, but physics is dead — a dropped sphere stays at its spawn
        # height and joint reads come back as garbage (-431602080.0 measured
        # on 6.0.1).
        #
        # Nothing else set up physics before the first robot, because
        # _ensure_physics_world is reached from create_robot's joint report —
        # i.e. one reference too late. Measured on 6.0.1-rc.7, cold-booted per
        # trial, two FR3s through the tools: initialise before either robot and
        # 150 steps run clean; initialise after the first and the second robot
        # brings 149 aborts. Stock Isaac Sim with the same two robots is clean
        # either way, and one robot alone never trips it, which is why every
        # single-robot flow missed this.
        #
        # PhysX only. Newton has no such fault (0 CUDA errors in every trial),
        # and priming it here actively breaks it: Newton builds its model when
        # physics comes up, so a model built on the empty scene left a
        # rigid-body-only stage frozen — a sphere dropped from z=2 stayed at
        # 2.000 where it had landed at 0.149, even though step reported the
        # rebuild. Scenes containing a robot were unaffected, which is exactly
        # the kind of partial break that ships unnoticed.
        # NOTE: an engine that cannot be identified ("unknown") primes, as
        # it always has -- V6 answers "unknown" whenever detection fails.
        if adapter.engine != adapter.ENGINE_NEWTON:
            adapter._ensure_physics_world()
        return {
            "status": "success",
            "message": f"Physics scene created at {scene_path}",
            # Which floor is authoritative, and whether this call supplied it.
            # A bare success reads as "I made you a ground plane" even when the
            # environment's own floor is the one objects will land on.
            "ground_plane": ground_plane,
            "ground_plane_created": ground_plane_created,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _clear_environment_contents(adapter: IsaacAdapterBase, stage) -> list:
    """Empty /Environment of loaded content while keeping the default lighting.

    Removes the reference arcs as well as the composed children: deleting only
    the children leaves the arc behind, and the next load_environment then
    composes a second reference on top of it.
    """
    env = stage.GetPrimAtPath("/Environment")
    if not env or not env.IsValid():
        return []
    # Snapshot paths, not prim handles. Deleting one child expires the handles
    # held for the others, and touching an expired one raises
    # "Accessed invalid expired 'Xform' prim" -- which aborted the whole clear,
    # so clear_scene failed outright on a stage that had an environment loaded.
    child_paths = []
    for child in env.GetChildren():
        try:
            if child.GetName() != "defaultLight":
                child_paths.append(str(child.GetPath()))
        except Exception:
            continue
    removed = []
    for path in child_paths:
        name = path.rsplit("/", 1)[-1]
        try:
            child = stage.GetPrimAtPath(path)
            if not child or not child.IsValid():
                continue
            try:
                child.GetReferences().ClearReferences()
            except Exception:
                pass
            adapter.delete_prim(path)
            removed.append(name)
        except Exception:
            # One stubborn child must not abort the rest of the clear.
            continue
    # Older callers referenced straight onto /Environment; undo that too, along
    # with any axis/unit reconciliation transform authored for it.
    try:
        from pxr import UsdGeom

        env = stage.GetPrimAtPath("/Environment")
        if env and env.IsValid():
            env.GetReferences().ClearReferences()
            UsdGeom.Xformable(env).ClearXformOpOrder()
    except Exception:
        pass
    return removed


def clear(adapter: IsaacAdapterBase, keep_physics: bool = False, keep_environment: bool = False) -> Dict[str, Any]:
    try:
        stage = adapter.get_stage()
        # Prims to never delete (system prims)
        keep_paths = {
            "/OmniverseKit_Persp",
            "/OmniverseKit_Front",
            "/OmniverseKit_Top",
            "/OmniverseKit_Right",
            "/Render",
            "/Environment",
        }
        # /Environment stays in keep_paths because it holds the stage's
        # defaultLight, and a stage with no light renders black -- which reads
        # as a broken sensor rather than a missing lamp. Its *contents* are a
        # different matter: a loaded environment used to survive clear_scene
        # entirely, so a later create_physics_scene stacked a second
        # ground under the first and "clear" left a 100 m world in place.
        # Sensors first: an initialized camera or lidar keeps its prim alive, so
        # clearing without releasing them left every camera ever created on the
        # stage, still rendering.
        # Delete each sensor prim by its own path rather than relying on the
        # root sweep below: deleting the *parent* does not release a camera the
        # way deleting the camera path does, so a bulk clear left cameras behind
        # for three passes while their render products kept rendering.
        # delete_prim releases the wrapper first, which is the sequence proven
        # to make the deletion stick.
        try:
            for cache_name in ("_camera_sensors", "_lidar_sensors"):
                for sensor_path in list(getattr(adapter, cache_name, {}) or {}):
                    adapter.delete_prim(sensor_path)
            adapter.release_all_sensors()
        except Exception:
            pass
        removed_environment = _clear_environment_contents(adapter, stage) if not keep_environment else []
        # Clear all root-level prims (robots created at root, etc.)
        root_prim = stage.GetPseudoRoot()
        for child in root_prim.GetChildren():
            path = str(child.GetPath())
            if path in keep_paths:
                continue
            if keep_physics and "Physics" in path:
                continue
            adapter.delete_prim(path)
        # The cached World still points at the prims just deleted. Left in place
        # it survives until something calls initialize_physics() on it, which
        # then raises "Accessed schema on invalid prim" and wedges every tool
        # that ensures a physics world. Drop it so the next call rebuilds
        # against the live stage.
        try:
            from isaacsim.core.api import World

            if World.instance() is not None:
                World.clear_instance()
        except Exception:
            pass  # Non-v5 runtimes / no World in play — nothing to invalidate.
        message = "Scene cleared"
        if removed_environment:
            message += f". Removed environment content: {', '.join(removed_environment)}"
            message += " (pass keep_environment=true to preserve it)"
        elif keep_environment:
            message += ". Environment preserved"
        result = {"status": "success", "message": message}
        if removed_environment:
            result["removed_environment"] = removed_environment
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_prims(
    adapter: IsaacAdapterBase,
    root_path: str = "/",
    prim_type: Optional[str] = None,
    recursive: bool = False,
) -> Dict[str, Any]:
    try:
        prims = adapter.list_prims(root_path=root_path, prim_type=prim_type, recursive=recursive)
        # Say which of the two listings this was. The shallow default reads as a
        # complete answer otherwise: during the 0.6.0 sweep "/World present"
        # after a clear_scene was taken for an empty scene while a lidar was
        # still parented under it.
        return {"status": "success", "prims": prims, "recursive": recursive}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_prim_info(adapter: IsaacAdapterBase, prim_path: str = "/") -> Dict[str, Any]:
    try:
        info = adapter.get_prim_info(prim_path)
        return {"status": "success", **info}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _get_env_library(adapter: IsaacAdapterBase) -> Dict[str, Dict[str, str]]:
    global _discovered_envs
    if _discovered_envs is not None:
        return _discovered_envs
    try:
        envs = adapter.discover_environments()
        if envs:
            _discovered_envs = envs
            print(f"Discovered {len(envs)} environments from asset server")
            return _discovered_envs
    except Exception as e:
        print(f"Environment discovery failed: {e}")
    _discovered_envs = {}
    return _discovered_envs


def list_environments(adapter: IsaacAdapterBase) -> Dict[str, Any]:
    library = _get_env_library(adapter)
    return {"status": "success", "environment_count": len(library), "environments": library}


# ── Environment reference reconciliation ───────────────────────────────────
#
# A referenced layer declares its own upAxis and metersPerUnit, and USD does not
# reconcile either when the reference is composed. Measured across the shipped
# library: 6 of 25 environments on 5.1 and 8 of 28 on 6.0 are Y-up, and 8 of 25 /
# 10 of 28 are authored in centimetres. Loading one of those into the Z-up,
# 1 m/unit stage this extension creates left it rotated 90 degrees AND 100x too
# large -- a "ground" standing on edge, 10 km across, with its floor at z=-5000.
# Neither adapter's add_reference_to_stage corrects it; this does.


def _asset_axis_and_units(url: str):
    """upAxis and metersPerUnit a referenced layer declares, or (None, None)."""
    try:
        from pxr import Sdf

        layer = Sdf.Layer.FindOrOpen(url)
        if layer is None:
            return None, None
        root = layer.pseudoRoot
        # USD's defaults when unauthored, not a guess: Y-up, centimetres.
        up = str(root.GetInfo("upAxis")) if root.HasInfo("upAxis") else "Y"
        mpu = float(root.GetInfo("metersPerUnit")) if root.HasInfo("metersPerUnit") else 0.01
        return up, mpu
    except Exception:
        return None, None


def _reference_conversion(adapter: IsaacAdapterBase, prim_path: str, url: str) -> Dict[str, Any]:
    """Report the axis/unit conversion USD applied to a freshly referenced prim.

    USD authors xformOp:rotateX:unitsResolve / xformOp:scale:unitsResolve itself
    when it composes a reference whose layer declares a different upAxis or
    metersPerUnit -- but only when it *creates* the prim. Referencing onto a prim
    that already exists (the old default /Environment, which the stage ships
    holding defaultLight) skips that resolution entirely, and the environment
    arrived rotated 90 degrees and 100x oversized: a ground standing on edge,
    10 km across, floor at z=-5000.

    So the fix is to reference onto a fresh child, not to correct by hand.
    Correcting on top of USD's own ops squares the scale -- measured 0.0001
    instead of 0.01, an environment 1 m across. This only reports what happened,
    so the conversion is visible rather than magic.
    """
    from pxr import UsdGeom

    asset_up, asset_mpu = _asset_axis_and_units(url)
    if asset_up is None:
        return {}
    stage = adapter.get_stage()
    if stage is None:
        return {}
    prim = stage.GetPrimAtPath(prim_path)
    resolved = []
    if prim and prim.IsValid():
        resolved = [
            op.GetName().split(":", 1)[-1]
            for op in UsdGeom.Xformable(prim).GetOrderedXformOps()
            if "unitsResolve" in op.GetName()
        ]
    stage_up = str(UsdGeom.GetStageUpAxis(stage))
    stage_mpu = float(UsdGeom.GetStageMetersPerUnit(stage) or 1.0)
    if asset_up == stage_up and abs((asset_mpu / stage_mpu if stage_mpu else 1.0) - 1.0) <= 1e-6:
        return {}
    applied: Dict[str, Any] = {"asset": {"up_axis": asset_up, "meters_per_unit": asset_mpu}}
    if asset_up != stage_up:
        applied["up_axis"] = f"{asset_up}->{stage_up}"
    if abs((asset_mpu / stage_mpu if stage_mpu else 1.0) - 1.0) > 1e-6:
        applied["scale"] = asset_mpu / stage_mpu
    applied["applied_by"] = "usd" if resolved else "none"
    if resolved:
        applied["ops"] = resolved
    return applied


def _collision_floor_outside(stage, root: str) -> Optional[str]:
    """Path of a collision floor on the stage that is NOT part of ``root``'s subtree.

    #37 stopped create_physics_scene stacking a plane on an environment, but
    that guard runs once, at create_physics_scene time. Called the other way
    round -- create_physics_scene first, then load_environment -- the
    environment's own floor arrives afterwards and the stage has two collision
    floors again, with the engine deciding which one wins. Measured on 6.0.1
    PhysX, 6.0.1 Newton and 5.1.0: two collision Planes in the reversed order,
    one in the documented order.

    The order cannot simply be enforced here (deleting a floor the caller
    authored would be worse), so the condition is reported instead.
    """
    from pxr import UsdPhysics

    try:
        for prim in stage.Traverse():
            if prim.GetTypeName() != "Plane":
                continue
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            path = str(prim.GetPath())
            if path == root or path.startswith(root.rstrip("/") + "/"):
                continue
            return path
    except Exception:
        return None
    return None


def _world_bounds(adapter: IsaacAdapterBase, prim_path: str) -> Dict[str, Any]:
    """Extent and floor height of a loaded environment, so the caller can place
    objects on it without a second round trip.

    ``floor_height`` and ``bounds_min_z`` are two different measurements and were
    once the same field. The bounding-box minimum is the environment's *lowest
    authored geometry* — trim, a recessed drain, a slightly sunk prop all drag it
    below the surface anything rests on. simple_warehouse reports -0.009 against
    a collision floor at 0.0, so placing on it embedded the object 9mm and that
    resolved as a settle or a jitter on the first step rather than as an error.
    The size of the error is a property of whichever environment is loaded, so it
    could not be corrected for once and reused.
    """
    try:
        from pxr import Usd, UsdGeom

        stage = adapter.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return {}
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if rng.IsEmpty():
            return {}
        mn, mx = rng.GetMin(), rng.GetMax()
        bounds: Dict[str, Any] = {
            "extent": [round(mx[i] - mn[i], 3) for i in range(3)],
            "bounds_min_z": round(mn[2], 3),
        }

        # Scoped to the environment: a groundPlane from an earlier
        # create_physics_scene is not this environment's floor.
        floor_path = _find_collision_floor(stage, root=prim_path)
        floor_z = _prim_world_z(stage, floor_path) if floor_path else None
        if floor_z is not None:
            bounds["floor_height"] = round(floor_z, 3)
            bounds["floor_height_source"] = "collision_floor"
            bounds["floor_prim"] = floor_path
        else:
            # An environment whose floor is a Mesh has no collision Plane to
            # measure. Falling back to the bbox minimum is the old, wrong
            # answer, so it is labelled rather than handed back looking
            # measured — the same treatment position_source and
            # velocity_warning give a value that may not mean what it looks
            # like. Omitting it instead would push the caller into raw USD to
            # find the floor, which is the round trip this field exists to
            # remove.
            bounds["floor_height"] = bounds["bounds_min_z"]
            bounds["floor_height_source"] = "bounds_min_z"
            bounds["floor_height_warning"] = (
                "No collision Plane was found in this environment, so floor_height is the "
                "bounding-box minimum — the lowest authored geometry, which is not necessarily "
                "the surface objects rest on. An object placed here may spawn embedded in the "
                "floor or hovering above it. Verify with a physics raycast or get_prim_info on "
                "the environment's floor prim before relying on it."
            )
        return bounds
    except Exception:
        return {}


def load_environment(
    adapter: IsaacAdapterBase, environment: Optional[str] = None, prim_path: Optional[str] = None
) -> Dict[str, Any]:
    try:
        if not environment:
            return {
                "status": "error",
                "message": "environment is required. Use scene.list_environments to see options.",
            }

        library = _get_env_library(adapter)
        q = environment.lower().strip()

        # Exact match
        match = library.get(q)
        matched_key = q if match else None

        # Fuzzy match
        if not match:
            for key, info in library.items():
                if q in key or q in info.get("description", "").lower():
                    match, matched_key = info, key
                    break

        if not match:
            available = list(library.keys())[:15]
            return {"status": "error", "message": f"Environment '{environment}' not found. Options: {available}"}

        assets_root = adapter.get_assets_root_path()
        full_path = assets_root + match["asset_path"]

        # Load under a named child rather than onto /Environment itself. That
        # prim also holds the stage's defaultLight, so sharing it meant the
        # reconciliation transform below rotated the light too, and clear_scene
        # could not remove the environment without removing the lighting.
        target = prim_path or f"/Environment/{matched_key or 'environment'}"

        # Re-loading must replace, not stack. Composing a second reference onto
        # a prim that already carries one silently changes the geometry -- the
        # same asset measured 10000x0x10000 on the first load and 100x100x0 on
        # the second -- and deleting the composed children does not remove the
        # arc that causes it.
        # get_stage() can be None before the stage is ready — the original code
        # never touched it, so a hard dependency here turned a working load into
        # "'NoneType' object has no attribute 'GetPrimAtPath'". Degrade instead.
        stage = adapter.get_stage()
        if stage is not None:
            existing = stage.GetPrimAtPath(target)
            if existing and existing.IsValid():
                try:
                    existing.GetReferences().ClearReferences()
                except Exception:
                    pass

        adapter.load_environment(full_path, target)
        corrections = _reference_conversion(adapter, target, full_path)
        bounds = _world_bounds(adapter, target)

        message = f"Loaded environment: {match['description']}"
        if corrections:
            message += f" (axis/units {corrections.get('applied_by')}-converted)"
        result = {"status": "success", "message": message, "prim_path": target}
        if corrections:
            result["corrections"] = corrections
        if bounds:
            result["bounds"] = bounds

        # Only a warning when BOTH floors are actually there: the environment's
        # own, and one that predates it. The floor test recognises a collision
        # Plane only, so a Mesh-floored environment cannot be checked this way
        # and stays silent rather than guessing.
        if stage is not None:
            foreign_floor = _collision_floor_outside(stage, target)
            if foreign_floor is not None and _find_collision_floor(stage, root=target) is not None:
                result["collision_floor_warning"] = (
                    f"The stage already carried a collision floor at {foreign_floor} before this "
                    "environment loaded, and the environment brings its own — so there are now two, "
                    "and which one objects land on is the physics engine's decision. Call "
                    "load_environment BEFORE create_physics_scene (that order adds no second floor), "
                    f"or delete {foreign_floor}."
                )

        if not bounds:
            # bounds carry floor_height, which is what lets a caller place
            # objects on the ground. Omitting them silently left the caller to
            # guess z on a stage whose scale it has not seen.
            result["warning"] = (
                "Could not compute bounds for this environment, so extent and floor_height are "
                "missing from this response. Query a specific prim with get_prim_info before "
                "placing objects, rather than assuming the ground is at z=0."
            )
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}
