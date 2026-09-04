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
def collision_api(monkeypatch):
    """The offline pxr stub has no UsdPhysics.CollisionAPI; supply one.

    Yielded so a test can assert the API was actually applied. Asserting only
    on the returned dict cannot distinguish "collision applied" from "collision
    silently skipped" -- both leave the same response.
    """
    from pxr import UsdPhysics

    api = MagicMock()
    monkeypatch.setattr(UsdPhysics, "CollisionAPI", api, raising=False)
    return api


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


def test_applies_collision_to_an_existing_uncollided_ground_plane(collision_api):
    """A Plane at our own path but without CollisionAPI must not be recreated.

    create_prim raises "A prim already exists at prim path" -- and because the
    physics scene is established first, the tool would report failure for work
    it had just completed. It must be adopted instead: given collision, since a
    plane that holds nothing up is not a floor.
    """
    stage = _Stage([_Prim("/World/groundPlane", "Plane", collision=False)])
    a = _adapter(stage)

    result = scene_handlers.create_physics(a)

    assert result["status"] == "success"
    a.create_prim.assert_not_called()
    assert result["ground_plane"] == "/World/groundPlane"
    # Without this the test passes even when collision is never applied: the
    # response is identical either way, so the returned dict cannot prove it.
    collision_api.Apply.assert_called_once()


def test_does_not_reapply_collision_to_a_plane_that_already_has_it(collision_api):
    """Applying CollisionAPI twice is wasted work on every repeat call."""
    stage = _Stage([_Prim("/World/groundPlane", "Plane", collision=True)])

    scene_handlers.create_physics(_adapter(stage))

    collision_api.Apply.assert_not_called()


# ── #37's guarantee only holds in one call order ─────────────────────────────


@pytest.fixture
def env_load(monkeypatch):
    """Mock the asset lookup and bounds so load_environment can be driven offline."""
    from pxr import Usd

    monkeypatch.setattr(
        scene_handlers,
        "_get_env_library",
        lambda adapter: {"simple_warehouse": {"description": "Simple Warehouse", "asset_path": "/w.usd"}},
        raising=False,
    )
    monkeypatch.setattr(scene_handlers, "_reference_conversion", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(scene_handlers, "_world_bounds", lambda *a, **k: {"floor_height": 0.0}, raising=False)
    monkeypatch.setattr(
        Usd,
        "PrimRange",
        lambda prim: [p for p in prim.__stage__.Traverse() if str(p.GetPath()).startswith(str(prim.GetPath()))],
        raising=False,
    )


def _env_adapter(stage):
    a = MagicMock()
    a.get_stage.return_value = stage
    a.get_assets_root_path.return_value = ""
    return a


ENV_ROOT = "/Environment/simple_warehouse"


def _env_stage(prims):
    stage = _Stage(prims)
    for p in stage.Traverse():
        p.__stage__ = stage
    root = _Prim(ENV_ROOT, "Xform")
    root.__stage__ = stage
    stage.add(root)
    return stage


def test_load_environment_warns_when_the_stage_already_had_a_collision_floor(env_load):
    """#37's guard runs once, at create_physics_scene time, so it only holds in one order.

    Reversed — create_physics_scene then load_environment — the environment's
    own floor arrives afterwards and the stage has two collision floors again.
    Measured on 6.0.1 PhysX, 6.0.1 Newton and 5.1.0: two collision Planes, both
    at z=0, while the documented order left exactly one.

    Nothing steered a caller to the safe order: the server's Scene Setup block
    never mentioned load_environment at all.
    """
    stage = _env_stage(
        [
            _Prim("/World/groundPlane", "Plane", collision=True),
            _Prim(ENV_ROOT + "/GroundPlane/CollisionPlane", "Plane", collision=True),
        ]
    )

    result = scene_handlers.load_environment(_env_adapter(stage), environment="simple_warehouse")

    assert result["status"] == "success"
    assert "collision_floor_warning" in result, (
        "loading an environment onto a stage that already has a collision floor leaves two, "
        "and which one wins is the physics engine's decision"
    )
    assert "/World/groundPlane" in result["collision_floor_warning"]


def test_load_environment_is_quiet_when_the_only_floor_is_the_environments_own(env_load):
    """Negative control: a warning that always fires would pass the test above."""
    stage = _env_stage([_Prim(ENV_ROOT + "/GroundPlane/CollisionPlane", "Plane", collision=True)])

    result = scene_handlers.load_environment(_env_adapter(stage), environment="simple_warehouse")

    assert result["status"] == "success"
    assert "collision_floor_warning" not in result
