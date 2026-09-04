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

"""Tests for the V6 adapter and version-aware dispatcher."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_v5(monkeypatch):
    mod = types.ModuleType("isaac_sim_mcp_extension.adapters.v5")

    class _V5:
        pass

    mod.IsaacAdapterV5 = _V5
    monkeypatch.setitem(sys.modules, "isaac_sim_mcp_extension.adapters.v5", mod)
    return _V5


@pytest.fixture
def fake_v6(monkeypatch):
    mod = types.ModuleType("isaac_sim_mcp_extension.adapters.v6")

    class _V6:
        pass

    mod.IsaacAdapterV6 = _V6
    monkeypatch.setitem(sys.modules, "isaac_sim_mcp_extension.adapters.v6", mod)
    return _V6


def test_get_adapter_returns_v5_when_version_5(fake_v5, fake_v6):
    from isaac_sim_mcp_extension.adapters import get_adapter

    with patch("isaac_sim_mcp_extension.adapters._detect_isaacsim_major_version", return_value=5):
        adapter = get_adapter()
    assert isinstance(adapter, fake_v5)


def test_get_adapter_returns_v6_when_version_6(fake_v5, fake_v6):
    from isaac_sim_mcp_extension.adapters import get_adapter

    with patch("isaac_sim_mcp_extension.adapters._detect_isaacsim_major_version", return_value=6):
        adapter = get_adapter()
    assert isinstance(adapter, fake_v6)


def test_get_adapter_falls_back_to_v5_when_detection_fails(fake_v5, fake_v6):
    from isaac_sim_mcp_extension.adapters import get_adapter

    with patch("isaac_sim_mcp_extension.adapters._detect_isaacsim_major_version", return_value=0):
        adapter = get_adapter()
    assert isinstance(adapter, fake_v5)


def test_detect_version_reads_isaacsim_core_version(monkeypatch):
    """When isaacsim.core.version.get_version returns a 6.x string, detection returns 6."""
    fake_version_mod = types.ModuleType("isaacsim.core.version")
    fake_version_mod.get_version = lambda: "6.0.0-rc.59+release.41464.5f2772bc.gl"
    fake_core_mod = types.ModuleType("isaacsim.core")
    fake_isaac_mod = types.ModuleType("isaacsim")
    monkeypatch.setitem(sys.modules, "isaacsim", fake_isaac_mod)
    monkeypatch.setitem(sys.modules, "isaacsim.core", fake_core_mod)
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", fake_version_mod)

    # Module already loaded in earlier tests; force a fresh import path
    import importlib

    import isaac_sim_mcp_extension.adapters as adapters_mod

    importlib.reload(adapters_mod)
    assert adapters_mod._detect_isaacsim_major_version() == 6


def test_detect_version_returns_zero_on_failure(monkeypatch):
    """When neither isaacsim.core.version nor a VERSION file is reachable, returns 0."""
    for name in list(sys.modules):
        if name.startswith("isaacsim"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    import importlib

    import isaac_sim_mcp_extension.adapters as adapters_mod

    importlib.reload(adapters_mod)
    assert adapters_mod._detect_isaacsim_major_version() == 0


def test_v6_create_prim_calls_experimental_define_prim(monkeypatch):
    """V6.create_prim must call isaacsim.core.experimental.utils.stage.define_prim."""
    define_prim_mock = MagicMock(return_value="prim-handle")
    fake_stage_mod = types.ModuleType("isaacsim.core.experimental.utils.stage")
    fake_stage_mod.define_prim = define_prim_mock
    fake_stage_mod.add_reference_to_stage = MagicMock()
    fake_stage_mod.delete_prim = MagicMock()
    for name in ("isaacsim", "isaacsim.core", "isaacsim.core.experimental", "isaacsim.core.experimental.utils"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "isaacsim.core.experimental.utils.stage", fake_stage_mod)

    # SimulationManager mock for __init__
    fake_sm_mod = types.ModuleType("isaacsim.core.simulation_manager")

    class _SM:
        @classmethod
        def get_active_physics_engine(cls):
            return "physx"

    fake_sm_mod.SimulationManager = _SM
    monkeypatch.setitem(sys.modules, "isaacsim.core.simulation_manager", fake_sm_mod)

    fake_version_mod = types.ModuleType("isaacsim.core.version")
    fake_version_mod.get_version = lambda: "6.0.0"
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", fake_version_mod)

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    adapter = v6_mod.IsaacAdapterV6()
    result = adapter.create_prim("/World/Foo", "Xform")
    define_prim_mock.assert_called_once_with("/World/Foo", type_name="Xform")
    assert result == "prim-handle"


def test_v6_ensure_physics_world_calls_simulation_manager(monkeypatch):
    """V6._ensure_physics_world must use SimulationManager, not World."""
    sm_calls = []

    class _SM:
        @classmethod
        def get_active_physics_engine(cls):
            return "newton"

        @classmethod
        def setup_simulation(cls, dt=None, device=None):
            sm_calls.append(("setup_simulation", dt))

        @classmethod
        def initialize_physics(cls):
            sm_calls.append(("initialize_physics",))

    fake_sm_mod = types.ModuleType("isaacsim.core.simulation_manager")
    fake_sm_mod.SimulationManager = _SM
    monkeypatch.setitem(sys.modules, "isaacsim.core.simulation_manager", fake_sm_mod)
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.0"))

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    adapter = v6_mod.IsaacAdapterV6()
    # Physics warming is guarded on a live stage (see
    # test_v6_never_warms_physics_without_a_stage), so provide one.
    monkeypatch.setattr(adapter, "get_stage", lambda: object())
    adapter._ensure_physics_world()
    assert ("setup_simulation", 1.0 / 60.0) in sm_calls
    assert ("initialize_physics",) in sm_calls
    # And confirm we picked up the engine
    assert adapter._engine == "newton"


def test_v6_set_joint_positions_calls_set_dof_position_targets(monkeypatch):
    """V6.set_joint_positions must build an Articulation and forward to set_dof_position_targets."""
    captured = {}

    class _Articulation:
        def __init__(self, paths):
            captured["paths"] = paths

        def is_physics_tensor_entity_initialized(self):
            return True

        def set_dof_position_targets(self, positions, indices=None):
            captured["positions"] = positions
            captured["indices"] = indices

        def get_dof_indices(self, names):
            captured["dof_indices_names"] = names

    fake_prims_mod = types.ModuleType("isaacsim.core.experimental.prims")
    fake_prims_mod.Articulation = _Articulation

    fake_warp_mod = types.ModuleType("warp")
    fake_warp_mod.array = lambda data, dtype=None: list(data)
    fake_warp_mod.float32 = "float32"

    monkeypatch.setitem(sys.modules, "warp", fake_warp_mod)
    monkeypatch.setitem(sys.modules, "isaacsim.core.experimental", types.ModuleType("isaacsim.core.experimental"))
    monkeypatch.setitem(sys.modules, "isaacsim.core.experimental.prims", fake_prims_mod)
    monkeypatch.setitem(
        sys.modules,
        "isaacsim.core.simulation_manager",
        types.SimpleNamespace(
            SimulationManager=type(
                "SM",
                (),
                {
                    "get_active_physics_engine": classmethod(lambda cls: "physx"),
                    "setup_simulation": classmethod(lambda cls, dt=None, device=None: None),
                    "initialize_physics": classmethod(lambda cls: None),
                },
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.0"))

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    adapter = v6_mod.IsaacAdapterV6()
    adapter.set_joint_positions("/World/Franka", [0.1, 0.2, 0.3])
    assert captured["paths"] == ["/World/Franka"]
    assert list(captured["positions"][0]) == [0.1, 0.2, 0.3]


def test_v6_get_simulation_state_includes_engine_and_version(monkeypatch):
    fake_timeline_iface = MagicMock()
    fake_timeline_iface.is_playing.return_value = False
    fake_timeline_iface.is_stopped.return_value = True
    fake_timeline_iface.get_current_time.return_value = 0.0
    fake_timeline_mod = types.ModuleType("omni.timeline")
    fake_timeline_mod.get_timeline_interface = lambda: fake_timeline_iface
    fake_omni_mod = types.ModuleType("omni")
    monkeypatch.setitem(sys.modules, "omni", fake_omni_mod)
    monkeypatch.setitem(sys.modules, "omni.timeline", fake_timeline_mod)
    fake_omni_mod.timeline = fake_timeline_mod

    class _Stage:
        def Traverse(self):
            return []

    fake_usd_mod = types.ModuleType("omni.usd")
    fake_usd_mod.get_context = lambda: types.SimpleNamespace(get_stage=lambda: _Stage())
    monkeypatch.setitem(sys.modules, "omni.usd", fake_usd_mod)
    fake_omni_mod.usd = fake_usd_mod

    monkeypatch.setitem(
        sys.modules,
        "isaacsim.core.simulation_manager",
        types.SimpleNamespace(
            SimulationManager=type(
                "SM",
                (),
                {
                    "get_active_physics_engine": classmethod(lambda cls: "newton"),
                },
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.0-rc.59"))

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    adapter = v6_mod.IsaacAdapterV6()
    state = adapter.get_simulation_state()
    assert state["engine"] == "newton"
    assert state["isaacsim_version"] == "6.0.0-rc.59"
    assert state["timeline_state"] == "stopped"


# The real isaacsim.core.version.get_version() on 6.0 is typed
# `-> tuple[str, str, str, str, str, str, str, str]` and returns
# (core, prerelease, major, minor, patch, pretag, prebuild, buildtag).
# Captured verbatim from a live Isaac Sim 6.0.1 runtime. Every other fake in
# this file returns a *string*, which is the 5.x shape the 6.x runtime never
# produces — so nothing here exercised the shape the adapter actually receives.
REAL_V6_VERSION_TUPLE = ("6.0.1", "rc.7", "6", "0", "1", "rc", "7", "release.42383.32955d8d.gl")


def test_detect_version_handles_real_6x_version_tuple(monkeypatch):
    """Detection must read the major from the tuple 6.0 actually returns."""
    fake_version_mod = types.ModuleType("isaacsim.core.version")
    fake_version_mod.get_version = lambda: REAL_V6_VERSION_TUPLE
    monkeypatch.setitem(sys.modules, "isaacsim", types.ModuleType("isaacsim"))
    monkeypatch.setitem(sys.modules, "isaacsim.core", types.ModuleType("isaacsim.core"))
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", fake_version_mod)

    import importlib

    import isaac_sim_mcp_extension.adapters as adapters_mod

    importlib.reload(adapters_mod)
    assert adapters_mod._detect_isaacsim_major_version() == 6


def test_v6_reports_a_human_version_from_the_real_tuple(monkeypatch):
    """isaacsim_version must be a version string, not the repr of a tuple.

    str(get_version()) yields "('6.0.1', 'rc.7', ...)" — a Python repr that
    leaks to every MCP client through get_simulation_state.
    """
    fake_timeline_iface = MagicMock()
    fake_timeline_iface.is_playing.return_value = False
    fake_timeline_iface.is_stopped.return_value = True
    fake_timeline_iface.get_current_time.return_value = 0.0
    fake_timeline_mod = types.ModuleType("omni.timeline")
    fake_timeline_mod.get_timeline_interface = lambda: fake_timeline_iface
    fake_omni_mod = types.ModuleType("omni")
    monkeypatch.setitem(sys.modules, "omni", fake_omni_mod)
    monkeypatch.setitem(sys.modules, "omni.timeline", fake_timeline_mod)
    fake_omni_mod.timeline = fake_timeline_mod

    class _Stage:
        def Traverse(self):
            return []

    fake_usd_mod = types.ModuleType("omni.usd")
    fake_usd_mod.get_context = lambda: types.SimpleNamespace(get_stage=lambda: _Stage())
    monkeypatch.setitem(sys.modules, "omni.usd", fake_usd_mod)
    fake_omni_mod.usd = fake_usd_mod

    monkeypatch.setitem(
        sys.modules,
        "isaacsim.core.simulation_manager",
        types.SimpleNamespace(
            SimulationManager=type("SM", (), {"get_active_physics_engine": classmethod(lambda cls: "physx")})
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "isaacsim.core.version",
        types.SimpleNamespace(get_version=lambda: REAL_V6_VERSION_TUPLE),
    )

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    adapter = v6_mod.IsaacAdapterV6()
    state = adapter.get_simulation_state()
    assert state["isaacsim_version"] == "6.0.1-rc.7"


def test_v6_engine_is_read_live_not_cached_at_construction(monkeypatch):
    """The engine must track SimulationManager, not a snapshot from __init__.

    Under isaac-sim.newton.sh the Newton backend registers ~2.7s AFTER this
    extension starts (measured on 6.0.1: mcp_extension at 3.978s,
    isaacsim.physics.newton at 6.649s), so at construction time the manager
    still reports the "physx" default. Caching there pins the adapter to the
    wrong backend for the whole session.
    """
    engine = {"value": "physx"}

    monkeypatch.setitem(
        sys.modules,
        "isaacsim.core.simulation_manager",
        types.SimpleNamespace(
            SimulationManager=type(
                "SM",
                (),
                {"get_active_physics_engine": classmethod(lambda cls: engine["value"])},
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.1"))

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    adapter = v6_mod.IsaacAdapterV6()
    assert adapter._engine == "physx"

    # Newton registers late in the boot sequence.
    engine["value"] = "newton"
    assert adapter._engine == "newton"


def test_v6_engine_reports_unknown_when_simulation_manager_is_unavailable(monkeypatch):
    """A missing/failing SimulationManager degrades to "unknown", never raises."""

    class _Broken:
        @classmethod
        def get_active_physics_engine(cls):
            raise RuntimeError("no manager")

    monkeypatch.setitem(
        sys.modules,
        "isaacsim.core.simulation_manager",
        types.SimpleNamespace(SimulationManager=_Broken),
    )
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.1"))

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    assert v6_mod.IsaacAdapterV6()._engine == "unknown"


def test_v6_import_urdf_uses_urdf_importer_class(monkeypatch, tmp_path):
    urdf_file = tmp_path / "robot.urdf"
    urdf_file.write_text("<robot name='r'/>")

    captured = {}

    class _Config:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

    class _Importer:
        def __init__(self, config):
            captured["importer_config"] = config

        def import_urdf(self, config=None):
            # 6.0: URDFImporter.import_urdf() converts the .urdf to a .usd on
            # disk and returns that generated USD path.
            return "/generated/robot.usd"

    def _fake_add_reference_to_stage(usd_path, prim_path):
        captured["add_reference"] = (usd_path, prim_path)
        return prim_path

    fake_urdf_mod = types.ModuleType("isaacsim.asset.importer.urdf")
    fake_urdf_mod.URDFImporter = _Importer
    fake_urdf_mod.URDFImporterConfig = _Config
    fake_stage_mod = types.ModuleType("isaacsim.core.experimental.utils.stage")
    fake_stage_mod.add_reference_to_stage = _fake_add_reference_to_stage
    monkeypatch.setitem(sys.modules, "isaacsim", types.ModuleType("isaacsim"))
    monkeypatch.setitem(sys.modules, "isaacsim.asset", types.ModuleType("isaacsim.asset"))
    monkeypatch.setitem(sys.modules, "isaacsim.asset.importer", types.ModuleType("isaacsim.asset.importer"))
    monkeypatch.setitem(sys.modules, "isaacsim.asset.importer.urdf", fake_urdf_mod)
    monkeypatch.setitem(sys.modules, "isaacsim.core", types.ModuleType("isaacsim.core"))
    monkeypatch.setitem(sys.modules, "isaacsim.core.experimental", types.ModuleType("isaacsim.core.experimental"))
    monkeypatch.setitem(
        sys.modules, "isaacsim.core.experimental.utils", types.ModuleType("isaacsim.core.experimental.utils")
    )
    monkeypatch.setitem(sys.modules, "isaacsim.core.experimental.utils.stage", fake_stage_mod)
    monkeypatch.setitem(
        sys.modules,
        "isaacsim.core.simulation_manager",
        types.SimpleNamespace(
            SimulationManager=type(
                "SM",
                (),
                {
                    "get_active_physics_engine": classmethod(lambda cls: "physx"),
                },
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.0"))

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    adapter = v6_mod.IsaacAdapterV6()
    result = adapter.import_urdf(str(urdf_file), prim_path="/World/robot")
    # 6.0 two-step API: config carries urdf_path + usd_path (the 5.x dest_path
    # kwarg is gone), then the generated USD is referenced into the live stage.
    assert captured["config"]["urdf_path"] == str(urdf_file)
    assert "usd_path" in captured["config"]
    assert "dest_path" not in captured["config"]
    assert captured["add_reference"] == ("/generated/robot.usd", "/World/robot")
    assert result == "/World/robot"


def test_get_simulation_state_detects_physics_scene_with_isa():
    """physics_dt detection must use IsA (typed schema), not HasAPI, on both adapters.

    Verified live against Isaac Sim 6.0.1: HasAPI(UsdPhysics.Scene) returns False
    on a PhysicsScene prim, so physics_dt stayed at 1/60 regardless of the scene's
    timeStepsPerSecond; IsA(UsdPhysics.Scene) matches correctly.
    """
    import os

    adapters_dir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "isaac.sim.mcp_extension",
        "isaac_sim_mcp_extension",
        "adapters",
    )
    for fname in ("v5.py", "v6.py"):
        with open(os.path.join(adapters_dir, fname)) as f:
            src = f.read()
        assert "IsA(UsdPhysics.Scene)" in src, f"{fname}: physics-scene check must use IsA"
        assert "HasAPI(UsdPhysics.Scene)" not in src, f"{fname}: HasAPI never matches a typed schema"


def _v6_with_stub_simulation_manager(monkeypatch, calls):
    """Build a V6 adapter whose SimulationManager records calls instead of running."""

    class _SM:
        @classmethod
        def get_active_physics_engine(cls):
            return "physx"

        @classmethod
        def _cleanup_stale_physics_scenes(cls):
            calls.append("cleanup")

        @classmethod
        def setup_simulation(cls, dt=None, device=None):
            calls.append("setup_simulation")

        @classmethod
        def initialize_physics(cls):
            calls.append("initialize_physics")

    monkeypatch.setitem(sys.modules, "isaacsim.core.simulation_manager", types.SimpleNamespace(SimulationManager=_SM))
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.1"))

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    return v6_mod.IsaacAdapterV6()


def test_v6_never_warms_physics_without_a_stage(monkeypatch):
    """setup_simulation() on a null stage is a native abort that kills Kit.

    Kit accepts MCP commands ~2.86s before it creates the USD stage (measured on
    6.0.1). setup_simulation() dereferences that stage in C++, so calling it in
    that window raises no Python exception — it prints
    "[Fatal] [omni.usd] attempted member lookup on NULL TfWeakPtr<UsdStage>" and
    aborts the process. It must never be reached without a stage.
    """
    calls = []
    adapter = _v6_with_stub_simulation_manager(monkeypatch, calls)
    monkeypatch.setattr(adapter, "get_stage", lambda: None)

    adapter._ensure_physics_world()

    assert calls == [], f"physics was warmed with no stage: {calls}"


def test_v6_warms_physics_once_a_stage_exists(monkeypatch):
    """The guard must not disable normal warming — only the no-stage case."""
    calls = []
    adapter = _v6_with_stub_simulation_manager(monkeypatch, calls)
    monkeypatch.setattr(adapter, "get_stage", lambda: object())

    adapter._ensure_physics_world()

    assert "setup_simulation" in calls
    assert "initialize_physics" in calls


def _install_fake_omni(monkeypatch, timeline, app):
    """Publish fake omni.timeline / omni.kit.app.

    `import omni.timeline` reads the attribute off the parent `omni` package, so
    patching sys.modules alone is not enough with conftest's omni stub.
    """
    fake_timeline = types.ModuleType("omni.timeline")
    fake_timeline.get_timeline_interface = lambda: timeline
    fake_app_mod = types.ModuleType("omni.kit.app")
    fake_app_mod.get_app = lambda: app
    fake_kit = types.ModuleType("omni.kit")
    fake_kit.app = fake_app_mod
    fake_omni = types.ModuleType("omni")
    fake_omni.timeline = fake_timeline
    fake_omni.kit = fake_kit
    monkeypatch.setitem(sys.modules, "omni", fake_omni)
    monkeypatch.setitem(sys.modules, "omni.timeline", fake_timeline)
    monkeypatch.setitem(sys.modules, "omni.kit", fake_kit)
    monkeypatch.setitem(sys.modules, "omni.kit.app", fake_app_mod)


def test_v6_step_pumps_only_for_newton(monkeypatch):
    """PhysX stepping must not pump the kit event loop; Newton has to.

    Pumping from inside the dispatch Task was believed unsafe everywhere: it can
    raise "Cannot enter into task <other> while another task <this handler> is
    being executed" for other pending kit tasks and invalidate the physics
    tensor view, and asyncio only logs it, so step returns a plausible result
    while the console shows the damage.

    Re-measured on 6.0.1: it did not reproduce on either backend — 60 pumped
    frames under isaac-sim.newton.sh logged no task errors and left the tensor
    view valid (get_velocities returned -9.8100). None of the PhysX-side step
    calls move Newton at all. Dropping a body from z=20 for 60 steps, where
    free fall predicts z=15.095:

        SimulationManager.step      z=20.0000  no motion
        SimulationView.step(dt)     z=20.0000  no motion
        physx.update_simulation     z=20.0000  no motion
        pumped app.update()         z=15.0133  runs

    That was once read as "no direct solver step advances Newton", which was
    wrong — NewtonStage.step_sim does, exactly, and is now the preferred path
    (see _newton_step_direct). The pump remains as the fallback for builds
    without it, and must stay behind the Newton branch either way: PhysX keeps
    SimulationManager.step because it is frame-exact and pumping changes its
    answers (-2.987 against -3.322 over the same fall).
    """
    import ast
    import os

    src_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "isaac.sim.mcp_extension",
        "isaac_sim_mcp_extension",
        "adapters",
        "v6.py",
    )
    with open(src_path) as f:
        text = f.read()
    tree = ast.parse(text)
    step_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "step":
            step_node = node
            break
    assert step_node is not None, "v6.step not found"

    def strip_comments(segment):
        return "\n".join(line.split("#", 1)[0] for line in segment.splitlines())

    # The pump has to sit inside a branch selected by the active engine, and the
    # other side of that branch has to be the exact PhysX step.
    guarded = False
    for node in ast.walk(step_node):
        if not isinstance(node, ast.If):
            continue
        body = strip_comments("\n".join(ast.get_source_segment(text, n) or "" for n in node.body))
        orelse = strip_comments("\n".join(ast.get_source_segment(text, n) or "" for n in node.orelse))
        if "get_app().update()" in body and "SimulationManager.step" in orelse:
            guarded = True
            break
    assert guarded, "the pump must be behind an engine branch whose other side is SimulationManager.step"

    code = strip_comments(ast.get_source_segment(text, step_node) or "")
    assert "newton" in code, "the branch must select on the Newton engine"
    assert "SimulationManager.step" in code


def test_v6_stop_does_not_call_a_nonexistent_reset_api():
    """SimulationManager.reset_simulation() does not exist on 6.0.1.

    It used to be called inside a bare except, so every stop_simulation raised
    AttributeError internally, swallowed it, and reported success.
    """
    import os

    src = os.path.join(
        os.path.dirname(__file__),
        "..",
        "isaac.sim.mcp_extension",
        "isaac_sim_mcp_extension",
        "adapters",
        "v6.py",
    )
    with open(src) as f:
        body = f.read()
    call_sites = [ln for ln in body.splitlines() if "reset_simulation()" in ln and not ln.strip().startswith("#")]
    assert call_sites == [], f"v6 calls a non-existent API: {call_sites}"


def test_v6_current_time_uses_the_physics_clock_not_the_timeline(monkeypatch):
    """current_time must come from SimulationManager.get_simulation_time().

    V6 advances physics with SimulationManager.step(), which never runs the
    timeline, so timeline.get_current_time() reports 0.0 for the whole step-only
    debug loop. The physics clock tracks each step and resets on stop.
    """

    class _Timeline:
        def is_playing(self):
            return False

        def is_stopped(self):
            return True

        def get_current_time(self):
            return 0.0  # timeline never advanced — the bug being fixed

    class _Stage:
        def Traverse(self):
            return []

    class _SM:
        @classmethod
        def get_active_physics_engine(cls):
            return "physx"

        @classmethod
        def get_simulation_time(cls):
            return 1.25

    monkeypatch.setitem(sys.modules, "isaacsim.core.simulation_manager", types.SimpleNamespace(SimulationManager=_SM))
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.1"))

    fake_timeline = types.ModuleType("omni.timeline")
    fake_timeline.get_timeline_interface = lambda: _Timeline()
    fake_usd = types.ModuleType("omni.usd")
    fake_usd.get_context = lambda: types.SimpleNamespace(get_stage=lambda: _Stage())
    fake_omni = types.ModuleType("omni")
    fake_omni.timeline = fake_timeline
    fake_omni.usd = fake_usd
    monkeypatch.setitem(sys.modules, "omni", fake_omni)
    monkeypatch.setitem(sys.modules, "omni.timeline", fake_timeline)
    monkeypatch.setitem(sys.modules, "omni.usd", fake_usd)

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    state = v6_mod.IsaacAdapterV6().get_simulation_state()

    assert state["current_time"] == 1.25, "current_time must track the physics clock"


class _ArmTimeline:
    """Timeline whose transitions are tick-driven, like kit's."""

    def __init__(self, stopped=True):
        self._stopped = stopped
        self.calls = []

    def is_stopped(self):
        return self._stopped

    def is_playing(self):
        return False

    def play(self):
        self.calls.append("play")

    def pause(self):
        self.calls.append("pause")


def _v6_for_arming(monkeypatch, timeline):
    calls = []
    adapter = _v6_with_stub_simulation_manager(monkeypatch, calls)
    monkeypatch.setattr(adapter, "get_stage", lambda: object())
    fake_timeline = types.ModuleType("omni.timeline")
    fake_timeline.get_timeline_interface = lambda: timeline
    fake_omni = types.ModuleType("omni")
    fake_omni.timeline = fake_timeline
    monkeypatch.setitem(sys.modules, "omni", fake_omni)
    monkeypatch.setitem(sys.modules, "omni.timeline", fake_timeline)
    return adapter


def test_v6_step_arms_a_reset_point_when_the_timeline_is_stopped(monkeypatch):
    """Without a Play, PhysX has no restore point and stop_simulation does nothing.

    play() and pause() are queued together so the timeline ends up paused without
    a single frame running free — verified on 6.0.1, where a cube left at z=50.0
    was still at exactly 50.0 afterwards.
    """
    timeline = _ArmTimeline(stopped=True)
    adapter = _v6_for_arming(monkeypatch, timeline)

    adapter._arm_reset_point()

    assert timeline.calls == ["play", "pause"], "must queue play+pause to arm the restore point"


def test_v6_does_not_disturb_a_timeline_that_is_already_running(monkeypatch):
    """Re-arming mid-run would move the restore point and interrupt a real Play."""
    timeline = _ArmTimeline(stopped=False)
    adapter = _v6_for_arming(monkeypatch, timeline)

    adapter._arm_reset_point()

    assert timeline.calls == []


def test_v6_arming_failure_never_blocks_stepping(monkeypatch):
    """Losing the ability to reset must not cost the caller their step."""

    class _Broken:
        def is_stopped(self):
            raise RuntimeError("timeline unavailable")

    adapter = _v6_for_arming(monkeypatch, _Broken())
    adapter._arm_reset_point()  # must not raise


class _FakePrim:
    def __init__(self, schemas=None, valid=True):
        self._schemas = list(schemas or [])
        self._valid = valid
        self.applied = []

    def IsValid(self):
        return self._valid

    def GetAppliedSchemas(self):
        return list(self._schemas)

    def ApplyAPI(self, name):
        self.applied.append(name)
        self._schemas.append(name)
        return True


def _v6_with_stage_prim(monkeypatch, prim):
    calls = []
    adapter = _v6_with_stub_simulation_manager(monkeypatch, calls)
    monkeypatch.setattr(adapter, "get_stage", lambda: types.SimpleNamespace(GetPrimAtPath=lambda _p: prim))
    return adapter


def test_v6_applies_the_sensor_schema_to_an_existing_camera_prim(monkeypatch):
    """RtxCamera adopts an existing prim without applying OmniSensorAPI.

    Pointing create_camera at a path that already holds a plain UsdGeom.Camera —
    which imported USD scenes routinely ship — failed on 6.0.1 with "Prim at
    <path> does not have the 'OmniSensorAPI' schema", while the same call on a
    fresh path succeeded.
    """
    prim = _FakePrim(schemas=[])  # a plain Camera: no applied API schemas
    adapter = _v6_with_stage_prim(monkeypatch, prim)

    adapter._apply_sensor_schema("/World/Cam")

    assert prim.applied == ["OmniSensorAPI"]


def test_v6_does_not_reapply_the_sensor_schema(monkeypatch):
    """A healthy RTX camera must be left untouched."""
    prim = _FakePrim(schemas=["OmniSensorAPI", "OmniRtxCameraExposureAPI_1"])
    adapter = _v6_with_stage_prim(monkeypatch, prim)

    adapter._apply_sensor_schema("/World/Cam")

    assert prim.applied == []


def test_v6_sensor_schema_noop_when_the_prim_does_not_exist(monkeypatch):
    """A path with no prim needs nothing — RtxCamera creates it correctly."""
    prim = _FakePrim(schemas=[], valid=False)
    adapter = _v6_with_stage_prim(monkeypatch, prim)

    adapter._apply_sensor_schema("/World/Cam")

    assert prim.applied == []


def _install_fake_replicator(monkeypatch, scheduled, pending_done):
    """Publish omni.replicator.core and capture what gets scheduled.

    `import omni.replicator.core` walks the parent packages, so each level has to
    exist as an attribute as well as in sys.modules. asyncio.ensure_future is
    patched on the real module rather than replaced wholesale.
    """
    import asyncio as real_asyncio

    async def _step_async(**kwargs):
        return None

    fake_core = types.ModuleType("omni.replicator.core")
    fake_core.orchestrator = types.SimpleNamespace(step_async=_step_async)
    fake_replicator = types.ModuleType("omni.replicator")
    fake_replicator.core = fake_core
    fake_omni = types.ModuleType("omni")
    fake_omni.replicator = fake_replicator
    monkeypatch.setitem(sys.modules, "omni", fake_omni)
    monkeypatch.setitem(sys.modules, "omni.replicator", fake_replicator)
    monkeypatch.setitem(sys.modules, "omni.replicator.core", fake_core)

    class _Task:
        def done(self):
            return pending_done

    def _ensure_future(coro, *a, **kw):
        scheduled.append(coro)
        coro.close()
        return _Task()

    monkeypatch.setattr(real_asyncio, "ensure_future", _ensure_future)


def test_v6_requests_a_render_frame_without_starting_the_timeline(monkeypatch):
    """An empty sensor must trigger a Replicator frame, scheduled not awaited.

    Measured on 6.0.1: orchestrator.run() starts the timeline (playing=True),
    which destroys frame-exact stepping, and the synchronous orchestrator.step()
    is refused from inside kit. step_async scheduled onto kit's loop captures one
    frame with the timeline left stopped.
    """
    scheduled = []
    calls = []
    adapter = _v6_with_stub_simulation_manager(monkeypatch, calls)
    _install_fake_replicator(monkeypatch, scheduled, pending_done=False)

    assert adapter._request_render_frame() is True
    assert len(scheduled) == 1, "must schedule exactly one render request"


def test_v6_does_not_queue_a_second_render_request_while_one_is_pending(monkeypatch):
    """Repeated captures on a blank camera must not pile up orchestrator tasks."""
    scheduled = []
    calls = []
    adapter = _v6_with_stub_simulation_manager(monkeypatch, calls)
    _install_fake_replicator(monkeypatch, scheduled, pending_done=False)

    adapter._request_render_frame()
    adapter._request_render_frame()
    adapter._request_render_frame()

    assert len(scheduled) == 1


def test_v6_requests_a_new_frame_once_the_previous_request_finished(monkeypatch):
    """A completed request must not block later captures from asking again."""
    scheduled = []
    calls = []
    adapter = _v6_with_stub_simulation_manager(monkeypatch, calls)
    _install_fake_replicator(monkeypatch, scheduled, pending_done=True)

    adapter._request_render_frame()
    adapter._request_render_frame()

    assert len(scheduled) == 2


def test_v6_get_simulation_state_survives_a_missing_stage(monkeypatch):
    """Kit accepts commands ~2.9s before it creates a stage.

    Traversing None there raised "'NoneType' object has no attribute 'Traverse'"
    — an opaque failure for a routine status query. The timeline state is still
    knowable, so it must be reported.
    """

    class _Timeline:
        def is_playing(self):
            return False

        def is_stopped(self):
            return True

        def get_current_time(self):
            return 0.0

    class _SM:
        @classmethod
        def get_active_physics_engine(cls):
            return "physx"

        @classmethod
        def get_simulation_time(cls):
            return 0.0

    monkeypatch.setitem(sys.modules, "isaacsim.core.simulation_manager", types.SimpleNamespace(SimulationManager=_SM))
    monkeypatch.setitem(sys.modules, "isaacsim.core.version", types.SimpleNamespace(get_version=lambda: "6.0.1"))

    fake_timeline = types.ModuleType("omni.timeline")
    fake_timeline.get_timeline_interface = lambda: _Timeline()
    fake_usd = types.ModuleType("omni.usd")
    fake_usd.get_context = lambda: types.SimpleNamespace(get_stage=lambda: None)  # no stage yet
    fake_omni = types.ModuleType("omni")
    fake_omni.timeline = fake_timeline
    fake_omni.usd = fake_usd
    monkeypatch.setitem(sys.modules, "omni", fake_omni)
    monkeypatch.setitem(sys.modules, "omni.timeline", fake_timeline)
    monkeypatch.setitem(sys.modules, "omni.usd", fake_usd)

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    state = v6_mod.IsaacAdapterV6().get_simulation_state()

    assert state["timeline_state"] == "stopped"
    assert state["physics_dt"] == 1.0 / 60.0


# Newton's MuJoCo solver has no mapping for GeoType.CONE (9). Hitting it makes
# Kit latch NewtonStage._init_failed = True, which permanently disables physics
# for the whole session — deleting the cone, clear_scene and rebuilding the
# PhysicsScene were all verified NOT to recover it on 6.0.1-rc.7. The adapter
# therefore has to refuse *before* initialize_physics(), and only on Newton:
# cones are fine under PhysX and on 5.1.
def _cone_stage_adapter(monkeypatch, engine, prims):
    """Build a V6 adapter over a stubbed stage of (type_name, has_articulation) prims."""

    class _Prim:
        def __init__(self, path, type_name, articulation):
            self._path = path
            self._type = type_name
            self._articulation = articulation

        def GetTypeName(self):
            return self._type

        def GetPath(self):
            return self._path

        def HasAPI(self, api):
            return self._articulation

    class _Stage:
        def Traverse(self):
            return [_Prim(path, type_name, art) for path, type_name, art in prims]

    # Keep conftest's omni stub (the extension needs omni.ext at import time)
    # and swap in only the stage-serving omni.usd.
    omni_mod = sys.modules["omni"]
    fake_usd_mod = types.ModuleType("omni.usd")
    fake_usd_mod.get_context = lambda: types.SimpleNamespace(get_stage=lambda: _Stage())
    monkeypatch.setitem(sys.modules, "omni.usd", fake_usd_mod)
    monkeypatch.setattr(omni_mod, "usd", fake_usd_mod, raising=False)

    monkeypatch.setitem(
        sys.modules,
        "isaacsim.core.simulation_manager",
        types.SimpleNamespace(
            SimulationManager=type(
                "SM",
                (),
                {"get_active_physics_engine": classmethod(lambda cls, e=engine: e)},
            )
        ),
    )

    import importlib

    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    importlib.reload(v6_mod)
    return v6_mod.IsaacAdapterV6()


def test_v6_refuses_newton_physics_init_on_a_cone_with_an_articulation(monkeypatch):
    adapter = _cone_stage_adapter(
        monkeypatch,
        "newton",
        [("/World/Cone", "Cone", False), ("/World/Arm", "Xform", True)],
    )
    with pytest.raises(RuntimeError) as excinfo:
        adapter._guard_newton_unsupported_geometry()
    message = str(excinfo.value)
    assert "/World/Cone" in message
    assert "PhysX" in message


def test_v6_allows_a_cone_when_no_articulation_is_present(monkeypatch):
    # Verified live: a cone alone simulates fine on Newton. Only the
    # cone + articulation combination reaches the MuJoCo conversion.
    adapter = _cone_stage_adapter(monkeypatch, "newton", [("/World/Cone", "Cone", False)])
    adapter._guard_newton_unsupported_geometry()


def test_v6_allows_a_cone_with_an_articulation_under_physx(monkeypatch):
    adapter = _cone_stage_adapter(
        monkeypatch,
        "physx",
        [("/World/Cone", "Cone", False), ("/World/Arm", "Xform", True)],
    )
    adapter._guard_newton_unsupported_geometry()


# Newton builds its model once and rebuilds it from the timeline STOP event. A
# step-only debug loop never stops, so after a clear_scene the model keeps the
# DELETED prims and never learns about the new ones — and Newton keeps stepping
# that phantom scene. Measured on 6.0.1-rc.7 through the MCP tools: clear_scene
# from a paused timeline, create a sphere at z=2, step 60, and step reports
# z=2.0 with zero velocity while model.body_label still reads ['/World/Ball']
# for a prim that no longer exists. sim_time and the step counter advance the
# whole time, so nothing looks wrong. The same drop after a stop_simulation
# lands correctly at z=0.149.
def _v6_function_src(name):
    import ast
    import os

    path = os.path.join(
        os.path.dirname(__file__), "..", "isaac.sim.mcp_extension", "isaac_sim_mcp_extension", "adapters", "v6.py"
    )
    with open(path) as f:
        text = f.read()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    return ""


def test_v6_step_rebuilds_a_stale_newton_model():
    src = _v6_function_src("step")
    assert "_refresh_newton_model_if_stale" in src, "step must rebuild a Newton model that no longer matches the stage"


def test_v6_newton_model_rebuild_is_newton_only_and_never_runs_while_playing():
    """PhysX must not be touched, and a rebuild under a live scene is unsafe."""
    src = _v6_function_src("_refresh_newton_model_if_stale")
    assert src, "_refresh_newton_model_if_stale not found"
    assert 'self._engine != "newton"' in src, "the rebuild must not touch PhysX"
    assert "is_playing" in src, "a rebuild underneath a running scene is what aborts the GPU pipeline"
    assert "_init_failed" in src, "a latched Newton failure (see the cone guard) must be left alone"


def test_v6_step_reprimes_physics_after_a_newton_model_rebuild():
    """The play/pump/pause cycle invalidates the tensor view the rebuild left valid.

    Without this the next joint read degrades to the drive-target fallback and
    echoes the caller's own command back — caught live by position_source.
    """
    src = _v6_function_src("step")
    assert "_ensure_physics_world" in src, "step must re-prime physics after rebuilding the Newton model"


def test_v6_articulation_calls_heal_a_stale_physics_view():
    """V6 needs the same heal-and-retry V5 got — PhysX was returning echoes.

    Measured at HEAD on 6.0.1 PhysX before this: set_joint_positions, create a
    prim, step, read — and the read fell through to the USD drive targets,
    reporting the commanded -0.4000 back as a measurement while the dropped
    sphere proved physics was running fine.
    """
    for name in ("get_joint_positions", "set_joint_positions", "_get_joint_names"):
        src = _v6_function_src(name)
        assert src, f"{name} not found"
        assert "_try_articulation" in src, f"{name} must heal a stale physics view and retry once"


def test_v6_physics_view_refresh_refuses_while_the_timeline_is_live():
    src = _v6_function_src("_refresh_stale_physics_view")
    assert src, "_refresh_stale_physics_view not found"
    assert "is_playing" in src, "rebuilding under a running scene is what aborts the GPU pipeline"
    assert "_warmup_needed" in src, "initialize_physics() early-returns unless the warmup flag is set"


def test_v6_get_prim_transform_labels_a_usd_fallback_on_newton():
    """Newton keeps simulated poses in Fabric, so an untagged USD read is a spawn pose.

    Measured on 6.0.1: a sphere resting on the ground still read z=2.0 from USD
    while get_prim_info reported it with no source at all.
    """
    src = _v6_function_src("get_prim_transform")
    assert src, "get_prim_transform not found"
    assert "position_warning" in src, "the caller has to be told it may be the spawn pose"


def test_v6_puts_the_fabric_pose_in_position_world_not_over_the_local_one():
    """The Fabric pose is a WORLD position (#39).

    It used to be written over `position`, which was parent-relative on every
    other runtime -- so one field carried two different frames depending on
    engine and prim type. It now lands in position_world, where it belongs, and
    the local pose is left alone.
    """
    src = _v6_function_src("get_prim_transform")
    assert '"position_world"' in src, "the Fabric pose must land in position_world"
    assert '"physics"' in src, "a physics-sourced world position must say so"
    assert 'transform["position"]' not in src, "the Fabric pose must not overwrite the local pose"


def test_v6_labels_the_stale_local_pose_when_the_fabric_read_succeeds(monkeypatch):
    """On Newton a *served* Fabric read leaves position_local at the spawn pose.

    The warning covering this only fires in the branch where the physics read
    FAILED. When it succeeds, position_world is replaced with the measured pose
    and position_local is left as the authored USD value -- stale, and now
    unlabelled, because the warning is in the other branch.

    That is #39 relocated rather than removed: the truthfulness of
    position_local varies by engine and prim type, silently. Before the frames
    were split the Fabric value overwrote the field outright, so no stale local
    value was exposed at all -- this is a new surface.

    The numbers here are the ones f4406df recorded as its own live control: a
    sphere under a parent at (1,2,0), spawned at local z=2.0, read back after 60
    steps. With the parent at z=0 a true local z would equal the world z, so
    position_local [0.25, 0, 2.0] against position_world [..., 0.09932] is stale
    by the whole fall.
    """
    import isaac_sim_mcp_extension.adapters.v6 as v6_mod

    adapter = v6_mod.IsaacAdapterV6()
    monkeypatch.setattr(type(adapter), "_engine", property(lambda self: "newton"))

    class _Prim:
        def IsValid(self):
            return True

    class _Stage:
        def GetPrimAtPath(self, path):
            return _Prim()

    adapter.get_stage = lambda: _Stage()
    adapter._try_articulation = lambda fn: ([1.25, 2.0, 0.09932], True)

    import pxr.UsdGeom as _usdgeom

    monkeypatch.setattr(_usdgeom, "Xformable", lambda prim: prim, raising=False)

    original = v6_mod.read_transform
    v6_mod.read_transform = lambda xformable: {
        "position_local": [0.25, 0.0, 2.0],
        "position_world": [1.25, 2.0, 2.0],
        "position_world_source": "usd",
    }
    try:
        out = adapter.get_prim_transform("/World/Rig/Ball")
    finally:
        v6_mod.read_transform = original

    assert out["position_world"] == [1.25, 2.0, 0.09932], "the measured pose belongs in position_world"
    assert out["position_world_source"] == "physics"
    assert "position_local_warning" in out, (
        "position_local is the authored spawn pose while position_world is measured — say so, "
        "or the two fields silently disagree about when they were taken"
    )
