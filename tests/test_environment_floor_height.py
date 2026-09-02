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

"""load_environment must report a floor you can stand on (issue #38).

bounds.floor_height was documented as the value that lets a caller "place
objects on the ground without a second query", but it was the bounding-box
minimum Z of the whole environment -- the lowest piece of authored geometry,
which trim, a recessed drain or a sunk prop drags below the floor. Measured on
simple_warehouse: floor_height -0.009 against a collision floor at 0.0, so
placing on the reported value embeds the object 9mm and resolves as a settle
or a jitter on the first physics step rather than as an error.

The two meanings are now separate fields: bounds_min_z is the bbox minimum
(honest, and what extent already means), floor_height is derived from the
environment's own collision floor.

Note the derivation is pure USD rather than a physics raycast. The issue could
only be *measured* on 5.1 and 6.0 PhysX because raycast_closest returns no hit
under Newton; a USD derivation is measurable on all three.
"""

from unittest.mock import MagicMock

import pytest
from isaac_sim_mcp_extension.handlers import scene as scene_handlers

ENV = "/Environment/simple_warehouse"
ENV_FLOOR = f"{ENV}/GroundPlane/CollisionPlane"

# Measured live on all three runtimes during the #37 sweep.
FLOOR_WORLD_Z = 0.0
BBOX_MIN_Z = -0.009


class _Prim:
    def __init__(self, path, type_name="Xform", collision=False, world_z=0.0, valid=True):
        self._path = path
        self._type = type_name
        self._collision = collision
        self.world_z = world_z
        self._valid = valid

    def IsValid(self):
        return self._valid

    def GetTypeName(self):
        return self._type

    def GetPath(self):
        return self._path

    def HasAPI(self, _api):
        return self._collision


class _Stage:
    def __init__(self, prims):
        self._prims = {p.GetPath(): p for p in prims}

    def Traverse(self):
        return list(self._prims.values())

    def GetPrimAtPath(self, path):
        return self._prims.get(str(path)) or _Prim(str(path), valid=False)

    def subtree(self, root):
        root = str(root)
        return [p for p in self._prims.values() if p.GetPath() == root or p.GetPath().startswith(root + "/")]


@pytest.fixture
def usd(monkeypatch):
    """Stub the pxr surface _world_bounds touches.

    ComputeLocalToWorldTransform is what makes this correct: _reference_conversion
    rotates and rescales Y-up / centimetre environments immediately before bounds
    are read, so the floor prim's *local* translate is not its height on the stage.
    """
    from pxr import Usd, UsdGeom, UsdPhysics

    monkeypatch.setattr(UsdPhysics, "CollisionAPI", MagicMock(), raising=False)

    class _TimeCode:
        @staticmethod
        def Default():
            return "default"

    monkeypatch.setattr(Usd, "TimeCode", _TimeCode, raising=False)
    monkeypatch.setattr(Usd, "PrimRange", lambda prim: prim.__stage__.subtree(prim.GetPath()), raising=False)
    monkeypatch.setattr(UsdGeom, "Tokens", type("T", (), {"default_": "default"}), raising=False)

    class _Xformable:
        def __init__(self, prim):
            self._prim = prim

        def ComputeLocalToWorldTransform(self, _tc):
            z = self._prim.world_z
            return type("M", (), {"ExtractTranslation": lambda self: (0.0, 0.0, z)})()

    monkeypatch.setattr(UsdGeom, "Xformable", _Xformable, raising=False)

    class _Range:
        def IsEmpty(self):
            return False

        def GetMin(self):
            return (-5.0, -5.0, BBOX_MIN_Z)

        def GetMax(self):
            return (5.0, 5.0, 3.0)

    class _BBoxCache:
        def __init__(self, *a, **k):
            pass

        def ComputeWorldBound(self, _prim):
            return type("B", (), {"ComputeAlignedRange": lambda self: _Range()})()

    monkeypatch.setattr(UsdGeom, "BBoxCache", _BBoxCache, raising=False)


def _adapter(stage):
    for p in stage._prims.values():
        p.__stage__ = stage
    a = MagicMock()
    a.get_stage.return_value = stage
    return a


def test_floor_height_comes_from_the_collision_floor_not_the_bbox(usd):
    """The #38 repro: simple_warehouse, floor at 0.0, bbox minimum at -0.009."""
    stage = _Stage(
        [
            _Prim(ENV, "Xform"),
            _Prim(ENV_FLOOR, "Plane", collision=True, world_z=FLOOR_WORLD_Z),
        ]
    )

    out = scene_handlers._world_bounds(_adapter(stage), ENV)

    assert out["floor_height"] == FLOOR_WORLD_Z
    assert out["bounds_min_z"] == BBOX_MIN_Z
    assert out["floor_height_source"] == "collision_floor"
    assert out["floor_prim"] == ENV_FLOOR


def test_extent_is_still_the_bounding_box(usd):
    """extent means a bbox and always did; #38 must not disturb it."""
    stage = _Stage([_Prim(ENV, "Xform"), _Prim(ENV_FLOOR, "Plane", collision=True)])

    out = scene_handlers._world_bounds(_adapter(stage), ENV)

    assert out["extent"] == [10.0, 10.0, round(3.0 - BBOX_MIN_Z, 3)]


def test_floor_outside_the_environment_is_not_the_environments_floor(usd):
    """A /World/groundPlane left by a previous create_physics_scene must not be
    reported as this environment's floor -- it is not part of it, and on a dirty
    stage it can sit at a completely different height."""
    stage = _Stage(
        [
            _Prim(ENV, "Xform"),
            _Prim("/World/groundPlane", "Plane", collision=True, world_z=0.0),
        ]
    )

    out = scene_handlers._world_bounds(_adapter(stage), ENV)

    assert out["floor_height_source"] == "bounds_min_z"
    assert out.get("floor_prim") is None


def test_floor_height_uses_the_world_transform(usd):
    """_reference_conversion rescales/rotates the environment just before this
    runs, so a local translate is not the height on the stage."""
    stage = _Stage(
        [
            _Prim(ENV, "Xform"),
            _Prim(ENV_FLOOR, "Plane", collision=True, world_z=1.25),
        ]
    )

    out = scene_handlers._world_bounds(_adapter(stage), ENV)

    assert out["floor_height"] == 1.25


def test_environment_without_a_collision_plane_is_labelled_not_silent(usd):
    """A Mesh-authored floor has no collision Plane. The value falls back to the
    bbox minimum -- which is the old, wrong answer -- so it must say so rather
    than hand back a number that looks measured."""
    stage = _Stage([_Prim(ENV, "Xform"), _Prim(f"{ENV}/Floor", "Mesh", collision=True)])

    out = scene_handlers._world_bounds(_adapter(stage), ENV)

    assert out["floor_height"] == BBOX_MIN_Z
    assert out["floor_height_source"] == "bounds_min_z"
    assert "floor_height_warning" in out
    assert "not" in out["floor_height_warning"].lower()
