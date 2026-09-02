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

"""create_physics must not stack a second collision floor (issue #37).

load_environment followed by create_physics_scene -- the order the server
instructions prescribe -- left two collision floors on the stage, because the
guard only ever asked whether */World/groundPlane* existed and never whether
the stage already had a floor. Measured 9/9 across 5.1, 6.0 PhysX and 6.0
Newton. In simple_warehouse both planes sit at z=0 so nothing looks wrong;
on an environment whose floor is elsewhere, which plane wins is PhysX's
decision rather than the caller's.

The rule is deliberately narrow: a collision-enabled prim of type Plane. A
Mesh floor still stacks, and that limitation is recorded on the issue --
widening it to "large flat collider" would let a tabletop or a wall panel
suppress a floor the caller genuinely needs.
"""

from unittest.mock import MagicMock

import pytest
from isaac_sim_mcp_extension.handlers import scene as scene_handlers


@pytest.fixture(autouse=True)
def _collision_api(monkeypatch):
    """The offline pxr stub has no UsdPhysics.CollisionAPI; supply one."""
    from pxr import UsdPhysics

    monkeypatch.setattr(UsdPhysics, "CollisionAPI", MagicMock(), raising=False)


class _Prim:
    def __init__(self, path, type_name="Xform", collision=False, valid=True):
        self._path = path
        self._type = type_name
        self._collision = collision
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
    def __init__(self, prims=()):
        self._prims = {p.GetPath(): p for p in prims}

    def Traverse(self):
        return list(self._prims.values())

    def GetPrimAtPath(self, path):
        return self._prims.get(str(path)) or _Prim(str(path), valid=False)

    def add(self, prim):
        self._prims[prim.GetPath()] = prim


def _adapter(stage):
    a = MagicMock()
    a.create_physics_scene.return_value = "/World/PhysicsScene"
    a.get_stage.return_value = stage
    # Creating the prim makes it exist, as it would on a real stage. The real
    # create_prim authors a Plane; collision is applied by create_physics after.
    a.create_prim.side_effect = lambda path, type_name: stage.add(_Prim(str(path), type_name, collision=False))
    return a


WAREHOUSE_FLOOR = "/Environment/simple_warehouse/GroundPlane/CollisionPlane"


def test_skips_ground_plane_when_the_environment_already_has_a_collision_floor():
    """The #37 repro: load_environment then create_physics_scene."""
    stage = _Stage([_Prim(WAREHOUSE_FLOOR, "Plane", collision=True)])
    a = _adapter(stage)

    result = scene_handlers.create_physics(a)

    assert result["status"] == "success"
    a.create_prim.assert_not_called()
    assert result["ground_plane_created"] is False
    assert result["ground_plane"] == WAREHOUSE_FLOOR


def test_creates_ground_plane_on_a_stage_with_no_floor():
    stage = _Stage()
    a = _adapter(stage)

    result = scene_handlers.create_physics(a)

    a.create_prim.assert_called_once_with("/World/groundPlane", "Plane")
    assert result["ground_plane_created"] is True
    assert result["ground_plane"] == "/World/groundPlane"


def test_a_plane_without_collision_is_not_a_floor():
    """A visual-only plane holds nothing up, so it must not suppress ours."""
    stage = _Stage([_Prim("/World/Backdrop", "Plane", collision=False)])
    a = _adapter(stage)

    result = scene_handlers.create_physics(a)

    a.create_prim.assert_called_once_with("/World/groundPlane", "Plane")
    assert result["ground_plane_created"] is True


def test_a_collision_cube_is_not_a_floor():
    """Pins the narrow rule: only type Plane counts.

    Widening this to "large flat collider" is a deliberate edit, not a drift --
    a tabletop or wall panel would otherwise suppress a needed ground plane.
    """
    stage = _Stage([_Prim("/World/Crate", "Cube", collision=True)])
    a = _adapter(stage)

    result = scene_handlers.create_physics(a)

    a.create_prim.assert_called_once_with("/World/groundPlane", "Plane")
    assert result["ground_plane_created"] is True


def test_second_call_reports_its_own_plane_rather_than_recreating_it():
    """The idempotency guard now runs through the same floor search."""
    stage = _Stage([_Prim("/World/groundPlane", "Plane", collision=True)])
    a = _adapter(stage)

    result = scene_handlers.create_physics(a)

    assert result["status"] == "success"
    a.create_prim.assert_not_called()
    assert result["ground_plane_created"] is False
    assert result["ground_plane"] == "/World/groundPlane"


def test_applies_collision_to_an_existing_uncollided_ground_plane():
    """A Plane at our own path but without CollisionAPI must not be recreated.

    create_prim raises "A prim already exists at prim path" -- and because the
    physics scene is established first, the tool would report failure for work
    it had just completed.
    """
    stage = _Stage([_Prim("/World/groundPlane", "Plane", collision=False)])
    a = _adapter(stage)

    result = scene_handlers.create_physics(a)

    assert result["status"] == "success"
    a.create_prim.assert_not_called()
    assert result["ground_plane"] == "/World/groundPlane"
