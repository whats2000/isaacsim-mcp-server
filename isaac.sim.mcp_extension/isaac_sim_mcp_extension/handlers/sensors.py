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

"""Sensor creation and data capture command handlers."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from ..adapters.base import IsaacAdapterBase
from .objects import prim_missing


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["sensors.create_camera"] = lambda **p: create_camera(adapter, **p)
    registry["sensors.capture_image"] = lambda **p: capture_image(adapter, **p)
    registry["sensors.create_lidar"] = lambda **p: create_lidar(adapter, **p)
    registry["sensors.get_point_cloud"] = lambda **p: get_point_cloud(adapter, **p)


def _prim_type(adapter: IsaacAdapterBase, prim_path: str) -> str:
    """USD type name of a prim, or "" when it cannot be read."""
    try:
        return str(adapter.get_stage().GetPrimAtPath(prim_path).GetTypeName())
    except Exception:
        return ""


def _free_prim_path(adapter: IsaacAdapterBase, prim_path: str, limit: int = 50) -> str:
    """First `<prim_path>_N` that no prim occupies, so a refusal can name it."""
    for n in range(2, limit + 2):
        candidate = f"{prim_path}_{n}"
        if not _prim_type(adapter, candidate):
            return candidate
    return f"{prim_path}_new"


def _first_rtx_camera(adapter: IsaacAdapterBase, prim_path: str) -> bool:
    """True when this is the first RTX camera of the Kit session (V6 only).

    Only 6.0 strands its first camera; V5 removes every one of them, so the
    warning would be false there.

    This used to ask whether `_camera_sensors` was empty, which is not the same
    question. V6 releases every cached sensor on timeline STOP — deliberately,
    since that is what lets a camera be deleted — so the cache empties on every
    play/stop cycle and the next camera was announced as the session's first.
    Measured on 6.0.1 PhysX: A1 warned, then after play/stop A3 warned, then
    after another cycle A5 warned, while A1 was the only stranded one. That
    inverts the workaround this warning exists to give.

    So record it once, on the adapter, on a name nothing else clears.
    """
    try:
        return adapter.note_first_rtx_camera(prim_path)
    except Exception:
        return False


def create_camera(
    adapter: IsaacAdapterBase,
    prim_path: str = "/World/Camera",
    position: Optional[Sequence[float]] = None,
    rotation: Optional[Sequence[float]] = None,
    resolution: Optional[Sequence[int]] = None,
    target: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    try:
        res = tuple(resolution) if resolution else (1280, 720)
        first_of_session = _first_rtx_camera(adapter, prim_path)
        _cam = adapter.create_camera(prim_path, resolution=res)

        aimed_at = None
        if target is not None:
            # Aiming needs a position to aim from. Fall back to the prim's
            # current one so target alone still works on an existing camera.
            eye = position
            if eye is None:
                try:
                    current = adapter.get_prim_transform(prim_path) or {}
                    # target is a world coordinate, so the eye must be one too.
                    # This used to read "position", which was the prim's
                    # parent-relative pose — a nested camera was aimed from the
                    # wrong frame and still produced a rotation, so it failed
                    # silently (#39). position_local is the last resort: for a
                    # prim directly under the stage root the two coincide.
                    eye = current.get("position_world") or current.get("position_local")
                except Exception:
                    eye = None
            if eye is not None:
                from ..adapters.transforms import look_at_euler

                aimed = look_at_euler(eye, target)
                if aimed is not None:
                    rotation, aimed_at = aimed, [float(v) for v in target]

        if position or rotation:
            adapter.set_prim_transform(prim_path, position=position, rotation=rotation)
        result = {"status": "success", "message": f"Camera created at {prim_path}", "prim_path": prim_path}
        if aimed_at is not None:
            result["aimed_at"] = aimed_at
            result["rotation"] = rotation
        if first_of_session:
            # Measured on 6.0.1-rc.7, cold-booted: the first RTX camera created
            # in a Kit session cannot be removed. delete_object reports success
            # and Replicator re-creates the prim and its render product a tick
            # later. Every camera after it deletes cleanly — four created and
            # four deleted, twice in a row, with only the first survivor left —
            # so this is one stuck camera per session, not the race it was
            # previously recorded as: the survivor is always the first *created*
            # even when they are deleted in reverse order. 5.1 does not have it
            # (4 of 4 removed there), hence the engine check.
            result["warning"] = (
                f"{prim_path} is the first RTX camera of this Isaac Sim session and cannot be "
                "removed later — delete_object will report success and the camera will come back. "
                "If this scene needs cameras added and removed, create one throwaway camera first "
                "and leave it in place; every camera after the first deletes cleanly. Restarting "
                "Isaac Sim also clears it."
            )
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


def capture_image(
    adapter: IsaacAdapterBase, prim_path: str = "/World/Camera", output_path: Optional[str] = None
) -> Dict[str, Any]:
    try:
        # Check the camera is there BEFORE touching the sensor machinery.
        # Capturing a path that does not exist used to build the whole RTX
        # pipeline for it: a Camera prim appeared at the typo'd path, together
        # with a render product and a five-node SDG OmniGraph, and Replicator
        # was then asked to render a frame for it. Three consequences, all
        # measured on 6.0.1-rc.7:
        #
        #   * the error said "No frame available from /World/NoCam yet", which
        #     sends the caller off to retry a path that was never a camera;
        #   * the stray camera and its render product are exactly the pair that
        #     "removing more than one RTX camera is unreliable" is about, so a
        #     typo could leave a sensor rendering for the life of the process;
        #   * on Newton it broke stepping outright — after one such call a
        #     sphere dropped from z=2 froze at 1.992 through 180 steps, where
        #     it otherwise lands at 0.149.
        if prim_missing(adapter, prim_path):
            return {
                "status": "error",
                "message": (
                    f"Prim not found: {prim_path}. Create the camera first with create_camera, "
                    "or pass the path of an existing one."
                ),
            }
        type_name = _prim_type(adapter, prim_path)
        if type_name and type_name != "Camera":
            return {
                "status": "error",
                "message": (
                    f"{prim_path} is a {type_name}, not a Camera, so it cannot produce an image. "
                    "Pass a camera prim, or create one with create_camera."
                ),
            }
        image_data = adapter.capture_camera_image(prim_path)
        # An RTX sensor with no frame yet yields an empty array, not an error.
        # Reporting that as success gave back {"shape": [0]} with status
        # "success", which a caller cannot tell apart from a captured image —
        # and with output_path set it fed an empty array to Image.fromarray.
        # Verified on Isaac Sim 6.0.1: in the step-only debug loop the timeline
        # never plays, Replicator's orchestrator therefore stays STOPPED
        # (/omni/replicator/captureOnPlay defaults to True), and every capture
        # returned an empty array while reporting success.
        if image_data is None or getattr(image_data, "size", 0) == 0:
            # Only say a render was requested if this adapter can actually
            # request one. V6 schedules a Replicator frame; V5 has no such path,
            # and telling a 5.1 caller to "call again to collect it" would send
            # them round a loop that never terminates.
            # Test the capability, not the current value: _render_request starts
            # as None, so checking it would give a V6 caller the V5 wording on
            # the first call — the one that actually schedules the render.
            requested = callable(getattr(adapter, "_request_render_frame", None))
            remedy = (
                "A render has been requested — call capture_image again to collect it."
                if requested
                else "Play the simulation, or capture again once a frame has rendered."
            )
            return {
                "status": "error",
                "message": (
                    f"No frame available from {prim_path} yet. RTX sensor data is produced by "
                    "Replicator, which by default only captures while the timeline is playing "
                    f"(/omni/replicator/captureOnPlay). {remedy}"
                ),
            }
        if output_path:
            from PIL import Image

            img = Image.fromarray(image_data)
            img.save(output_path)
            return {"status": "success", "message": f"Image saved to {output_path}", "output_path": output_path}
        return {
            "status": "success",
            "message": "Image captured",
            "shape": list(image_data.shape) if hasattr(image_data, "shape") else None,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _timeline_is_live(adapter: IsaacAdapterBase) -> bool:
    """True when the timeline is playing or paused mid-run.

    Best effort: an adapter that cannot answer must not block the create.
    """
    try:
        state = (adapter.get_simulation_state() or {}).get("timeline_state")
    except Exception:
        return False
    return state in ("playing", "paused")


def create_lidar(
    adapter: IsaacAdapterBase,
    prim_path: str = "/World/Lidar",
    position: Optional[Sequence[float]] = None,
    rotation: Optional[Sequence[float]] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        # A path that already holds a Camera cannot host a working lidar.
        # On 5.1 a deleted or cleared lidar leaves its prim behind, resurrected
        # as a Camera (#25). Creating a lidar there binds LidarRtx to that
        # Camera and the sensor never yields a single point: measured 0 of 15
        # reads, twice, on a path that had held a lidar before, while fresh
        # paths in the same session read 33-40%. Reporting success for that is
        # how #31 looked like flaky sensor timing for so long — the caller
        # retries an empty read forever and nothing says why.
        existing = _prim_type(adapter, prim_path)
        if existing == "Camera":
            # Name a path that is actually free. "use a different prim path"
            # leaves the caller to invent one, and an agent mid-task tends to
            # retry the same one instead — the error has to carry the next step,
            # not just the diagnosis.
            suggested = _free_prim_path(adapter, prim_path)
            return {
                "status": "error",
                "message": (
                    f"{prim_path} already holds a Camera prim, left behind by a lidar that was "
                    "deleted or cleared earlier in this session — Isaac re-creates the prim as a "
                    "Camera and it cannot be removed. A lidar created here would report success "
                    f"and never return a point. Retry with prim_path={suggested!r}, which is free, "
                    "or restart Isaac Sim to clear the stray."
                ),
                "prim_path": prim_path,
                "suggested_prim_path": suggested,
            }

        adapter.create_lidar(prim_path, config=config)
        if position or rotation:
            adapter.set_prim_transform(prim_path, position=position, rotation=rotation)
        result = {"status": "success", "message": f"Lidar created at {prim_path}", "prim_path": prim_path}
        warnings = []
        if config and not getattr(adapter, "SUPPORTS_LIDAR_CONFIG", True):
            # Asking for a hardware model and silently receiving a generic
            # sensor is a wrong answer, not a lesser one.
            warnings.append(
                f"config={config!r} was not applied: this Isaac Sim version creates a generic "
                "lidar and sets hardware presets as schema attributes afterwards, which this tool "
                "does not do. The sensor works, but it is not the requested model — set the "
                "omni:sensor:* attributes with execute_script if the preset matters."
            )
        # The annotators bind to a render product only for a sensor created on a
        # stopped timeline (#31). Created mid-play it never fills, and the empty
        # read then sends the caller into the "retry, several attempts is
        # normal" loop, which cannot succeed for this sensor.
        if _timeline_is_live(adapter):
            warnings.append(
                "This lidar was created while the timeline was running, and its annotators bind "
                "to a render product only when the sensor is created on a stopped timeline — it "
                "will very likely never return a point. Call stop_simulation, delete this prim, "
                "and create the lidar again before reading it."
            )
        if warnings:
            result["warning"] = " ".join(warnings)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_point_cloud(
    adapter: IsaacAdapterBase,
    prim_path: str = "/World/Lidar",
    max_points: Optional[int] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        if prim_missing(adapter, prim_path):
            return {
                "status": "error",
                "message": (
                    f"Prim not found: {prim_path}. Create the sensor first with create_lidar, "
                    "or pass the path of an existing one."
                ),
            }
        pc = adapter.get_lidar_point_cloud(prim_path)
        point_count = len(pc) if pc is not None else 0
        # An empty read has three different causes and they need different
        # answers. The message used to give one -- "call play_simulation" --
        # which is wrong advice two times out of three: it is baffling when you
        # are already playing, and actively misleading when the lidar is simply
        # looking at nothing (a sensor buried inside a robot returned 491 points
        # in testing, and would return 0 if fully enclosed).
        if point_count == 0:
            timeline_state = ""
            try:
                timeline_state = str((adapter.get_simulation_state() or {}).get("timeline_state", "")).lower()
            except Exception:
                pass

            if not timeline_state:
                # Could not tell. Cover both, rather than guessing and sending
                # the caller down the wrong path.
                message = (
                    f"No lidar data from {prim_path}. If the timeline is not running, call "
                    "play_simulation — RTX lidar is produced by Replicator only while the sim runs. "
                    "If it is already playing, retry: the sensor fills only on frames where a "
                    "rotation completes. If it never fills, check the lidar is not inside geometry."
                )
            elif timeline_state != "playing":
                message = (
                    f"No lidar data from {prim_path}: the timeline is {timeline_state}. RTX lidar is "
                    "produced by Replicator only while the sim runs, and one rendered frame is not "
                    "enough — call play_simulation, then read again."
                )
            else:
                # Playing, so frames are flowing. This annotator only yields on
                # frames where a sweep completes, so an empty read is usually
                # "not this frame" and a retry fixes it.
                message = (
                    f"No completed sweep from {prim_path} on this frame. The sensor fills only on "
                    "frames where a rotation completes, so retry the same call — several attempts "
                    "over a few seconds is normal. If it never fills, check the lidar is not inside "
                    "geometry: one placed at a robot's own origin sees only the robot."
                )

            return {
                "status": "error",
                "message": message,
                "point_count": 0,
                "timeline_state": timeline_state or "unknown",
            }
        # The decoded cloud used to be dropped here and only its length
        # returned, so a tool named get_lidar_point_cloud could not produce a
        # point cloud. Returning all of it is not the answer either: a sweep is
        # tens of thousands of points and megabytes of JSON, which is ruinous
        # for an agent's context. So the default is decision-grade summary, with
        # the points available on request and the full array writable to disk --
        # the same escape hatch capture_image offers via output_path.
        #
        # Deliberately plain Python rather than numpy: the unit suite stubs
        # numpy, and a summary that only works inside Kit is a summary nobody
        # tests.
        rows = [(float(p[0]), float(p[1]), float(p[2])) for p in pc]
        min_x = min_y = min_z = float("inf")
        max_x = max_y = max_z = float("-inf")
        nearest_sq = float("inf")
        nearest_point = rows[0]
        for x, y, z in rows:
            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
            if z < min_z:
                min_z = z
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y
            if z > max_z:
                max_z = z
            d2 = x * x + y * y + z * z
            if d2 < nearest_sq:
                nearest_sq, nearest_point = d2, (x, y, z)

        result: Dict[str, Any] = {
            "status": "success",
            "message": f"Got {point_count} points",
            "point_count": point_count,
            "bounds": {
                "min": [round(min_x, 4), round(min_y, 4), round(min_z, 4)],
                "max": [round(max_x, 4), round(max_y, 4), round(max_z, 4)],
            },
            "nearest": {
                "distance": round(nearest_sq**0.5, 4),
                "point": [round(v, 4) for v in nearest_point],
            },
            "frame": "sensor-local coordinates, meters",
        }

        if output_path:
            # .npy so the caller gets every point at full precision;
            # numpy.load(path) reads it back as an (N, 3) array.
            try:
                import numpy as np

                target = output_path if str(output_path).endswith(".npy") else f"{output_path}.npy"
                np.save(target, np.asarray(rows, dtype="float32"))
                result["output_path"] = target
            except Exception as exc:
                result["output_error"] = f"could not write {output_path}: {exc}"

        if max_points:
            limit = max(1, int(max_points))
            if point_count > limit:
                # Even stride rather than the first N: a sweep is ordered by
                # beam, so the head of the array is one slice of the scene.
                stride = -(-point_count // limit)
                sample = rows[::stride][:limit]
                result["sampled"] = True
                result["sample_stride"] = stride
            else:
                sample = rows
                result["sampled"] = False
            result["points"] = [[round(v, 4) for v in row] for row in sample]

        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}
