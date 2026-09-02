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

"""create_physics must be safe to call twice."""

from unittest.mock import MagicMock

import pytest
from isaac_sim_mcp_extension.handlers import scene as scene_handlers


@pytest.fixture(autouse=True)
def _collision_api(monkeypatch):
    """The offline pxr stub has no UsdPhysics.CollisionAPI; supply one."""
    from pxr import UsdPhysics

    monkeypatch.setattr(UsdPhysics, "CollisionAPI", MagicMock(), raising=False)


class _FakePrim:
    def __init__(self, valid):
        self._valid = valid

    def IsValid(self):
        return self._valid

    def HasAPI(self, _api):
        return True


class _FakeStage:
    def __init__(self, existing):
        self.existing = set(existing)

    def GetPrimAtPath(self, path):
        return _FakePrim(str(path) in self.existing)

    def Traverse(self):
        # create_physics searches the stage for an existing collision floor
        # (#37). Without this the search raises into its fallback, and these
        # tests would pass through the error path rather than the real one.
        return [_FakeFloor(path) for path in sorted(self.existing)]


class _FakeFloor(_FakePrim):
    """A prim the floor search can classify: type and path, collision via HasAPI."""

    def __init__(self, path):
        super().__init__(True)
        self._path = path

    def GetTypeName(self):
        return "Plane" if self._path.endswith("groundPlane") else "Xform"

    def GetPath(self):
        return self._path


def _adapter(existing):
    a = MagicMock()
    a.create_physics_scene.return_value = "/World/PhysicsScene"
    stage = _FakeStage(existing)
    a.get_stage.return_value = stage
    # Creating the prim makes it exist, as it would on a real stage.
    a.create_prim.side_effect = lambda path, _type: stage.existing.add(str(path))
    return a


def test_ground_plane_created_when_missing():
    a = _adapter(existing=[])
    result = scene_handlers.create_physics(a)
    assert result["status"] == "success"
    a.create_prim.assert_called_once_with("/World/groundPlane", "Plane")


def test_second_call_does_not_recreate_ground_plane():
    """create_prim raises "A prim already exists" on a repeat call.

    The physics scene is established before the ground plane, so an unguarded
    create_prim made the tool report failure for work it had already done, and
    the message named groundPlane rather than anything the caller asked for.
    """
    a = _adapter(existing=["/World/groundPlane"])
    result = scene_handlers.create_physics(a)
    assert result["status"] == "success"
    a.create_prim.assert_not_called()


# ── duplicate PhysicsScene ───────────────────────────────────────────────────


class _ScenePrim:
    def __init__(self, path, type_name):
        self._path = path
        self._type = type_name

    def IsValid(self):
        return True

    def GetTypeName(self):
        return self._type

    def GetPath(self):
        return type("P", (), {"pathString": self._path})()


class _SceneStage:
    def __init__(self, prims):
        self._prims = {p: _ScenePrim(p, t) for p, t in prims.items()}

    def Traverse(self):
        return list(self._prims.values())

    def GetPrimAtPath(self, path):
        found = self._prims.get(path)
        if found is not None:
            return found
        missing = _ScenePrim(path, "")
        missing.IsValid = lambda: False
        return missing


def _adapter_with_stage(stage):
    """A minimal concrete adapter exposing only what _find_physics_scene needs."""
    from isaac_sim_mcp_extension.adapters.base import IsaacAdapterBase

    class _A(IsaacAdapterBase):
        def get_stage(self):
            return stage

    _A.__abstractmethods__ = frozenset()
    return _A()


def test_finds_the_stage_default_physics_scene():
    """Isaac Sim 6.0 ships /PhysicsScene on a new stage.

    Creating a second scene at /World/PhysicsScene makes the tensor backend
    refuse state reads — get_velocities fails and the callers swallow it into
    [0, 0, 0]. Verified on 6.0.1: a falling body reported zero velocity with two
    scenes present and -1.9840 m/s once the duplicate was removed.
    """
    adapter = _adapter_with_stage(_SceneStage({"/PhysicsScene": "PhysicsScene"}))

    assert adapter._find_physics_scene(preferred_path="/World/PhysicsScene") == "/PhysicsScene"


def test_prefers_the_requested_path_when_it_already_holds_a_scene():
    stage = _SceneStage({"/PhysicsScene": "PhysicsScene", "/World/PhysicsScene": "PhysicsScene"})
    adapter = _adapter_with_stage(stage)

    assert adapter._find_physics_scene(preferred_path="/World/PhysicsScene") == "/World/PhysicsScene"


def test_reports_no_scene_on_an_empty_stage():
    adapter = _adapter_with_stage(_SceneStage({"/World": "Xform"}))

    assert adapter._find_physics_scene(preferred_path="/World/PhysicsScene") is None
