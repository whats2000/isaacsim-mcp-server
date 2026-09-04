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

"""get_prim_info must say which frame a position is in (issue #39).

transform.position was the prim's *parent-relative* pose, and nothing in the
response or the tool description said so. For a prim under a transformed parent
the number is not where the object is: a child at local (0.25, 0, 0) under a
parent at (1, 2, 0.5) reported [0.25, 0, 0]. Reproduced 9/9 across 5.1, 6.0
PhysX and 6.0 Newton.

Two things made it easy to walk into. actual_size in the same response *is*
world-scale-aware, so one response mixed a local position with a world-space
size. And robot links are addressed as /World/Franka/fr3_hand_tcp -- Isaac's FR3
is a flat hierarchy rooted at the articulation, so with the robot at the origin
(the default) local and world coincide and the tool looks correct. Put the robot
anywhere else and the same call silently returns base-relative coordinates.

Worse than filed: on 6.0 Newton the Fabric branch overwrote position with a
*world* value, so one field carried two different frames depending on runtime
and prim type.

The fix names both frames explicitly. There is deliberately no bare "position":
a field called position sitting beside position_world reads as the default one,
which is the exact misreading that caused this.
"""

import pytest
from isaac_sim_mcp_extension.adapters import transforms

# ── fakes ────────────────────────────────────────────────────────────────────


class _Matrix:
    """Just enough Gf.Matrix4d for read_transform: translation, rows, rotation."""

    def __init__(self, translation=(0.0, 0.0, 0.0), rows=None):
        self._t = tuple(float(v) for v in translation)
        self._rows = rows or [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

    def ExtractTranslation(self):
        return self._t

    def __getitem__(self, i):
        return self._rows[i]

    def Orthonormalize(self):
        return True

    def ExtractRotation(self):
        return self

    def Decompose(self, *_axes):
        return (0.0, 0.0, 0.0)


class _Xformable:
    def __init__(self, local, world=None, world_raises=False):
        self._local = local
        self._world = world
        self._world_raises = world_raises

    def GetLocalTransformation(self):
        return self._local

    def ComputeLocalToWorldTransform(self, _tc):
        if self._world_raises:
            raise RuntimeError("no world transform available")
        return self._world


@pytest.fixture(autouse=True)
def _gf(monkeypatch):
    """read_transform needs Gf.Matrix4d / Gf.Vec3d and Usd.TimeCode."""
    from pxr import Gf, Usd

    class _Vec3d:
        def __init__(self, *c):
            self._c = [float(v) for v in c]

        def GetLength(self):
            return sum(v * v for v in self._c) ** 0.5

    monkeypatch.setattr(Gf, "Matrix4d", lambda m: m, raising=False)
    monkeypatch.setattr(Gf, "Vec3d", _Vec3d, raising=False)
    monkeypatch.setattr(Usd, "TimeCode", type("TC", (), {"Default": staticmethod(lambda: "default")}), raising=False)


# ── the frame split ──────────────────────────────────────────────────────────

LOCAL = (0.25, 0.0, 0.0)
WORLD = (1.25, 2.0, 0.5)


def test_reports_both_frames_under_explicit_names():
    """The issue's own repro: child at local (0.25,0,0), parent at (1,2,0.5)."""
    x = _Xformable(_Matrix(LOCAL), _Matrix(WORLD))

    out = transforms.read_transform(x)

    assert out["position_local"] == [0.25, 0.0, 0.0]
    assert out["position_world"] == [1.25, 2.0, 0.5]
    assert out["position_world_source"] == "usd"


def test_there_is_no_bare_position_field():
    """A field named "position" beside position_world reads as the default one.

    That misreading is what put a base-relative end-effector coordinate into a
    grasp calculation. Both frames are named, or neither is trustworthy.
    """
    x = _Xformable(_Matrix(LOCAL), _Matrix(WORLD))

    out = transforms.read_transform(x)

    assert "position" not in out


def test_local_and_world_coincide_at_the_origin():
    """Why this went unnoticed: a robot created at the default origin.

    Isaac's FR3 is a flat hierarchy rooted at the articulation, so with the
    robot at the origin the two frames agree and the tool looks correct.
    """
    x = _Xformable(_Matrix((1.0, 0.0, 0.0)), _Matrix((1.0, 0.0, 0.0)))

    out = transforms.read_transform(x)

    assert out["position_local"] == out["position_world"]


def test_an_unavailable_world_transform_is_absent_not_guessed():
    """Falling back to the local value under a world name is the #39 bug again."""
    x = _Xformable(_Matrix(LOCAL), world_raises=True)

    out = transforms.read_transform(x)

    assert out["position_local"] == [0.25, 0.0, 0.0]
    assert "position_world" not in out
    assert "position_world_source" not in out
    assert "position_world_warning" in out


def test_rotation_and_scale_are_still_reported():
    x = _Xformable(_Matrix(LOCAL), _Matrix(WORLD))

    out = transforms.read_transform(x)

    assert out["rotation"] == [0.0, 0.0, 0.0]
    assert out["rotation_units"] == "degrees"
    assert out["scale"] == [1.0, 1.0, 1.0]


# ── create_camera(target=) aimed from the wrong frame ────────────────────────


def test_camera_aim_falls_back_to_the_world_position_not_the_local_one():
    """create_camera(target=) mixed frames on a nested camera.

    With no explicit position it reads the camera's current pose and passes it
    to look_at_euler as the eye point -- but `target` is a world coordinate. A
    parent-relative eye against a world target aims at nothing in particular,
    and it fails silently: a rotation is produced either way. Surfaced by #39
    rather than reported, because both values used to be called "position".
    """
    from unittest.mock import MagicMock

    from isaac_sim_mcp_extension.handlers import sensors as sensor_handlers

    seen = {}

    def _look_at(eye, target, *a, **k):
        seen["eye"] = list(eye)
        return [0.0, 0.0, 0.0]

    import isaac_sim_mcp_extension.adapters.transforms as tmod

    original = tmod.look_at_euler
    tmod.look_at_euler = _look_at
    try:
        adapter = MagicMock()
        adapter.get_prim_transform.return_value = {
            "position_local": [0.25, 0.0, 0.0],
            "position_world": [1.25, 2.0, 0.5],
            "position_world_source": "usd",
        }
        sensor_handlers.create_camera(adapter, prim_path="/World/Rig/Cam", target=[0.0, 0.0, 0.0])
    finally:
        tmod.look_at_euler = original

    assert seen.get("eye") == [1.25, 2.0, 0.5], (
        f"camera aimed from {seen.get('eye')} — the parent-relative pose — against a world target"
    )


def test_camera_aim_is_written_in_the_parent_frame():
    """look_at_euler returns a WORLD orientation; set_prim_transform writes a LOCAL op.

    Fixing the eye point (#39) left the other half of the same frame mix in
    place. Under a parent that is only translated the two orientations
    coincide, which is why the original live control -- a camera under a parent
    at (5,0,3) -- measured correct. Under a *rotated* parent the camera is
    aimed wrong and still silently: a rotation is produced either way.

    Measured on 6.0.1 PhysX, 6.0.1 Newton and 5.1.0, parent rotated 90 deg
    about Z: the camera missed a world-origin target by 74.651 deg, while the
    same rig without the parent rotation was exact. create_camera returned the
    identical rotation [59.036243, -0.0, 90.0] in both cases -- the world value,
    written through unconverted.
    """
    from unittest.mock import MagicMock

    import isaac_sim_mcp_extension.adapters.transforms as tmod
    from isaac_sim_mcp_extension.handlers import sensors as sensor_handlers

    world_aim = [59.036243, -0.0, 90.0]
    parent_frame_aim = [11.0, 22.0, 33.0]

    original_look_at = tmod.look_at_euler
    original_to_local = getattr(tmod, "local_euler_for_world_rotation", None)
    tmod.look_at_euler = lambda eye, target, *a, **k: list(world_aim)
    tmod.local_euler_for_world_rotation = lambda stage, prim_path, euler: list(parent_frame_aim)
    try:
        adapter = MagicMock()
        adapter.get_prim_transform.return_value = {
            "position_local": [0.0, 0.0, 0.0],
            "position_world": [5.0, 0.0, 3.0],
            "position_world_source": "usd",
        }
        result = sensor_handlers.create_camera(adapter, prim_path="/World/Rig/Cam", target=[0.0, 0.0, 0.0])
    finally:
        tmod.look_at_euler = original_look_at
        if original_to_local is None:
            delattr(tmod, "local_euler_for_world_rotation")
        else:
            tmod.local_euler_for_world_rotation = original_to_local

    written = adapter.set_prim_transform.call_args.kwargs.get("rotation")
    assert written == parent_frame_aim, (
        f"camera orientation written as {written} — the world look-at value, authored as a local xform op"
    )
    assert result["rotation"] == parent_frame_aim, "the response must report the rotation actually applied"


def test_camera_aim_labels_an_unconvertible_parent_frame():
    """A world orientation written as a local op is only right at the stage root.

    When the parent transform cannot be read there is still an aim to author,
    and the world value is the best available one — but for a nested camera it
    may be wrong by the parent's rotation. Say so, the way position_source and
    floor_height_warning label a value that may not mean what it looks like.
    """
    from unittest.mock import MagicMock

    import isaac_sim_mcp_extension.adapters.transforms as tmod
    from isaac_sim_mcp_extension.handlers import sensors as sensor_handlers

    world_aim = [59.036243, -0.0, 90.0]

    original_look_at = tmod.look_at_euler
    original_to_local = getattr(tmod, "local_euler_for_world_rotation", None)
    tmod.look_at_euler = lambda eye, target, *a, **k: list(world_aim)
    tmod.local_euler_for_world_rotation = lambda stage, prim_path, euler: None
    try:
        adapter = MagicMock()
        adapter.get_prim_transform.return_value = {"position_world": [5.0, 0.0, 3.0]}
        result = sensor_handlers.create_camera(adapter, prim_path="/World/Rig/Cam", target=[0.0, 0.0, 0.0])
    finally:
        tmod.look_at_euler = original_look_at
        if original_to_local is None:
            delattr(tmod, "local_euler_for_world_rotation")
        else:
            tmod.local_euler_for_world_rotation = original_to_local

    assert result["rotation"] == world_aim
    assert "rotation_warning" in result, "an unconverted world aim must be labelled, not handed back looking measured"


# ── observe_prims fell back to the local frame too ───────────────────────────


def _adapter_src(filename, func):
    import ast
    import os

    path = os.path.join(
        os.path.dirname(__file__), "..", "isaac.sim.mcp_extension", "isaac_sim_mcp_extension", "adapters", filename
    )
    with open(path) as f:
        src = f.read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{func} not found in {filename}")


def _unpaired_local_reads(src):
    """Position reads in `step` that take the local frame on their own.

    `step` reads a position in several places, and each one must ask for
    position_world first and fall back to position_local only if it is absent.
    A substring check cannot enforce that: it is satisfied by a single
    surviving world read while every other site silently reverts to the local
    frame. Measured — reverting two of the three sites in each adapter left the
    whole suite green.

    So pair them structurally instead. Every `transform.get("position_local")`
    must be the right-hand side of `transform.get("position_world") or ...`;
    anything else is a site reading the parent-relative pose as though it were
    a measurement.
    """
    import ast

    def _reads(node, key):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "transform"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == key
        )

    tree = ast.parse(src)
    paired = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for left, right in zip(node.values, node.values[1:]):
                if _reads(left, "position_world") and _reads(right, "position_local"):
                    paired.add(id(right))

    unpaired = [n for n in ast.walk(tree) if _reads(n, "position_local") and id(n) not in paired]
    world_reads = [n for n in ast.walk(tree) if _reads(n, "position_world")]
    return unpaired, world_reads


@pytest.mark.parametrize("filename", ["v5.py", "v6.py"])
def test_observe_prims_falls_back_to_the_world_frame(filename):
    """step(observe_prims=) mixed frames in the same field.

    Its primary branch reads PhysX (v5) or the tensor view (v6), both of which
    report WORLD positions. The USD fallback beneath it reported the
    parent-relative one, so which frame `position` meant depended on whether the
    physics read happened to succeed — invisible to the caller, and the field
    most used for measuring motion.
    """
    src = _adapter_src(filename, "step")

    unpaired, world_reads = _unpaired_local_reads(src)

    assert world_reads, f"{filename}: observe_prims must fall back to the world frame"
    assert not unpaired, (
        f"{filename}: {len(unpaired)} position read(s) in step() take position_local without "
        "preferring position_world — the parent-relative pose reported as though it were measured"
    )


@pytest.mark.parametrize("filename", ["v5.py", "v6.py"])
def test_observe_prims_does_not_read_the_retired_position_key(filename):
    """`transform.get("position", [0, 0, 0])` would now silently report the origin.

    read_transform no longer emits a bare "position", so a stale .get() with a
    default does not raise — it hands back [0, 0, 0] as though it were measured.
    That is the worst available failure mode for this field.
    """
    src = _adapter_src(filename, "step")

    assert 'transform.get("position"' not in src, f"{filename}: retired key would silently yield [0, 0, 0]"
