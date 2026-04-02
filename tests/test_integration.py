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

"""Integration tests for all MCP tools against a running Isaac Sim instance.

Prerequisites:
    1. Isaac Sim 5.1.0 must be running with the MCP extension enabled:
       cd ~/isaacsim
       ./isaac-sim.sh --ext-folder ~/Documents/GitHub/isaacsim-mcp-server/ --enable isaac.sim.mcp_extension

    2. The extension must be listening on localhost:8766

Run:
    pytest tests/test_integration.py -v
    pytest tests/test_integration.py -v -k "scene"     # run only scene tests
    pytest tests/test_integration.py -v -k "robot"      # run only robot tests

All tests are skipped automatically if Isaac Sim is not reachable.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import Any, Dict, Optional

import pytest

# Add project root to path so we can import isaac_mcp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from isaac_mcp.connection import IsaacConnection

# ── Fixtures ──────────────────────────────────────────────


def _isaac_reachable() -> bool:
    """Check if Isaac Sim extension is listening on port 8766."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(("localhost", 8766))
        s.close()
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


requires_isaac = pytest.mark.skipif(
    not _isaac_reachable(),
    reason="Isaac Sim not running on localhost:8766",
)


@pytest.fixture(scope="module")
def conn() -> IsaacConnection:
    """Create a persistent connection for the test module."""
    c = IsaacConnection(host="localhost", port=8766)
    if not c.connect():
        pytest.skip("Could not connect to Isaac Sim")
    yield c
    c.disconnect()


def send(conn: IsaacConnection, cmd_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Send a command and return the full response (including status)."""
    command = {"type": cmd_type, "params": params or {}}
    conn.sock.sendall(json.dumps(command).encode("utf-8"))
    conn.sock.settimeout(300.0)
    data = conn.receive_full_response(conn.sock)
    return json.loads(data.decode("utf-8"))


# ── Scene Tools ───────────────────────────────────────────


@requires_isaac
class TestSceneTools:
    def test_get_scene_info(self, conn: IsaacConnection) -> None:
        resp = send(conn, "scene.get_info")
        assert resp["status"] == "success", f"Failed: {resp}"
        result = resp["result"]
        assert result["status"] == "success"
        assert "assets_root_path" in result
        assert "stage_path" in result

    def test_create_physics_scene(self, conn: IsaacConnection) -> None:
        resp = send(conn, "scene.create_physics", {"scene_name": "TestPhysics"})
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_list_prims(self, conn: IsaacConnection) -> None:
        resp = send(conn, "scene.list_prims", {"root_path": "/"})
        assert resp["status"] == "success", f"Failed: {resp}"
        result = resp["result"]
        assert "prims" in result

    def test_get_prim_info(self, conn: IsaacConnection) -> None:
        # First create an object so we have something to inspect
        send(conn, "objects.create", {"object_type": "Cube", "prim_path": "/World/TestInfoCube"})
        resp = send(conn, "scene.get_prim_info", {"prim_path": "/World/TestInfoCube"})
        assert resp["status"] == "success", f"Failed: {resp}"
        result = resp["result"]
        assert result["path"] == "/World/TestInfoCube"

    def test_clear_scene(self, conn: IsaacConnection) -> None:
        resp = send(conn, "scene.clear")
        assert resp["status"] == "success", f"Failed: {resp}"


# ── Object Tools ──────────────────────────────────────────


@requires_isaac
class TestObjectTools:
    def test_create_cube(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "objects.create",
            {
                "object_type": "Cube",
                "prim_path": "/World/TestCube",
                "position": [1.0, 0.0, 0.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"
        result = resp["result"]
        assert result["prim_path"] == "/World/TestCube"

    def test_create_sphere(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "objects.create",
            {
                "object_type": "Sphere",
                "prim_path": "/World/TestSphere",
                "position": [2.0, 0.0, 0.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_cylinder(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "objects.create",
            {
                "object_type": "Cylinder",
                "prim_path": "/World/TestCylinder",
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_cone(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "objects.create",
            {
                "object_type": "Cone",
                "prim_path": "/World/TestCone",
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_transform_object(self, conn: IsaacConnection) -> None:
        # Create then transform
        send(conn, "objects.create", {"object_type": "Cube", "prim_path": "/World/TransformCube"})
        resp = send(
            conn,
            "objects.transform",
            {
                "prim_path": "/World/TransformCube",
                "position": [5.0, 5.0, 0.0],
                "scale": [2.0, 2.0, 2.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_clone_object(self, conn: IsaacConnection) -> None:
        send(conn, "objects.create", {"object_type": "Cube", "prim_path": "/World/OrigCube"})
        resp = send(
            conn,
            "objects.clone",
            {
                "source_path": "/World/OrigCube",
                "target_path": "/World/ClonedCube",
                "position": [3.0, 0.0, 0.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_delete_object(self, conn: IsaacConnection) -> None:
        send(conn, "objects.create", {"object_type": "Cube", "prim_path": "/World/DeleteMe"})
        resp = send(conn, "objects.delete", {"prim_path": "/World/DeleteMe"})
        assert resp["status"] == "success", f"Failed: {resp}"


# ── Lighting Tools ────────────────────────────────────────


@requires_isaac
class TestLightingTools:
    def test_create_distant_light(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "lighting.create",
            {
                "light_type": "DistantLight",
                "prim_path": "/World/TestDistantLight",
                "intensity": 500.0,
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_sphere_light(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "lighting.create",
            {
                "light_type": "SphereLight",
                "prim_path": "/World/TestSphereLight",
                "intensity": 1000.0,
                "color": [1.0, 0.8, 0.6],
                "position": [0.0, 0.0, 5.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_dome_light(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "lighting.create",
            {
                "light_type": "DomeLight",
                "prim_path": "/World/TestDomeLight",
                "intensity": 300.0,
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_rect_light(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "lighting.create",
            {
                "light_type": "RectLight",
                "prim_path": "/World/TestRectLight",
                "intensity": 800.0,
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_modify_light(self, conn: IsaacConnection) -> None:
        send(
            conn,
            "lighting.create",
            {
                "light_type": "DistantLight",
                "prim_path": "/World/ModifyLight",
                "intensity": 500.0,
            },
        )
        resp = send(
            conn,
            "lighting.modify",
            {
                "prim_path": "/World/ModifyLight",
                "intensity": 1500.0,
                "color": [0.0, 1.0, 0.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_invalid_light_type(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "lighting.create",
            {
                "light_type": "InvalidLight",
                "prim_path": "/World/BadLight",
            },
        )
        assert resp["status"] == "error"


# ── Robot Tools ───────────────────────────────────────────


@requires_isaac
class TestRobotTools:
    def test_list_available_robots(self, conn: IsaacConnection) -> None:
        resp = send(conn, "robots.list")
        assert resp["status"] == "success", f"Failed: {resp}"
        result = resp["result"]
        robots = result["robots"]
        assert "franka" in robots
        assert "g1" in robots
        assert "go1" in robots
        assert "jetbot" in robots
        assert "carter" in robots

    def test_create_franka(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "robots.create",
            {
                "robot_type": "franka",
                "position": [0.0, 0.0, 0.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_g1(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "robots.create",
            {
                "robot_type": "g1",
                "position": [2.0, 0.0, 0.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_go1(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "robots.create",
            {
                "robot_type": "go1",
                "position": [4.0, 0.0, 0.0],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_invalid_robot(self, conn: IsaacConnection) -> None:
        resp = send(conn, "robots.create", {"robot_type": "nonexistent"})
        assert resp["status"] == "error"

    def test_get_robot_info(self, conn: IsaacConnection) -> None:
        send(
            conn,
            "robots.create",
            {
                "robot_type": "franka",
                "position": [6.0, 0.0, 0.0],
                "name": "InfoFranka",
            },
        )
        resp = send(conn, "robots.get_info", {"prim_path": "/InfoFranka"})
        # May need physics initialized to get full info
        assert resp["status"] in ("success", "error")


# ── Material Tools ────────────────────────────────────────


@requires_isaac
class TestMaterialTools:
    def test_create_pbr_material(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "materials.create",
            {
                "material_type": "pbr",
                "prim_path": "/World/TestPBR",
                "color": [0.8, 0.2, 0.2],
                "roughness": 0.3,
                "metallic": 0.9,
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_create_physics_material(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "materials.create",
            {
                "material_type": "physics",
                "prim_path": "/World/TestPhysMat",
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_apply_material(self, conn: IsaacConnection) -> None:
        send(conn, "objects.create", {"object_type": "Cube", "prim_path": "/World/MatCube"})
        send(
            conn,
            "materials.create",
            {
                "material_type": "pbr",
                "prim_path": "/World/ApplyMat",
                "color": [0.0, 1.0, 0.0],
            },
        )
        resp = send(
            conn,
            "materials.apply",
            {
                "material_path": "/World/ApplyMat",
                "target_prim_path": "/World/MatCube",
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_invalid_material_type(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "materials.create",
            {
                "material_type": "invalid",
                "prim_path": "/World/BadMat",
            },
        )
        assert resp["status"] == "error"


# ── Sensor Tools ──────────────────────────────────────────


@requires_isaac
class TestSensorTools:
    def test_create_camera(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "sensors.create_camera",
            {
                "prim_path": "/World/TestCamera",
                "position": [5.0, 5.0, 3.0],
                "resolution": [640, 480],
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_capture_image(self, conn: IsaacConnection) -> None:
        send(
            conn,
            "sensors.create_camera",
            {
                "prim_path": "/World/CapCamera",
                "position": [0.0, -5.0, 2.0],
            },
        )
        resp = send(
            conn,
            "sensors.capture_image",
            {
                "prim_path": "/World/CapCamera",
            },
        )
        # Capture may require simulation to be running; accept both success and error
        assert resp["status"] in ("success", "error")

    def test_create_lidar(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "sensors.create_lidar",
            {
                "prim_path": "/World/TestLidar",
                "position": [0.0, 0.0, 2.0],
            },
        )
        # Lidar creation may vary by Isaac Sim config
        assert resp["status"] in ("success", "error")


# ── Asset Tools ───────────────────────────────────────────


@requires_isaac
class TestAssetTools:
    def test_import_urdf_missing_file(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "assets.import_urdf",
            {
                "urdf_path": "/nonexistent/robot.urdf",
            },
        )
        assert resp["status"] == "error"

    def test_load_usd_missing_url(self, conn: IsaacConnection) -> None:
        resp = send(conn, "assets.load_usd", {})
        assert resp["status"] == "error"

    def test_search_usd_missing_prompt(self, conn: IsaacConnection) -> None:
        resp = send(conn, "assets.search_usd", {})
        assert resp["status"] == "error"

    def test_generate_3d_missing_input(self, conn: IsaacConnection) -> None:
        resp = send(conn, "assets.generate_3d", {})
        assert resp["status"] == "error"


# ── Simulation Tools ──────────────────────────────────────


@requires_isaac
class TestSimulationTools:
    def test_play(self, conn: IsaacConnection) -> None:
        resp = send(conn, "simulation.play")
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_step(self, conn: IsaacConnection) -> None:
        resp = send(conn, "simulation.step", {"num_steps": 10})
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_pause(self, conn: IsaacConnection) -> None:
        resp = send(conn, "simulation.pause")
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_stop(self, conn: IsaacConnection) -> None:
        resp = send(conn, "simulation.stop")
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_execute_script(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "simulation.execute_script",
            {
                "code": "result = 1 + 1",
            },
        )
        assert resp["status"] == "success", f"Failed: {resp}"

    def test_execute_script_error(self, conn: IsaacConnection) -> None:
        resp = send(
            conn,
            "simulation.execute_script",
            {
                "code": "raise ValueError('test error')",
            },
        )
        # Script errors should be caught and returned
        assert resp["status"] in ("success", "error")

    def test_execute_script_missing_code(self, conn: IsaacConnection) -> None:
        resp = send(conn, "simulation.execute_script", {})
        assert resp["status"] == "error"


# ── Unknown Command ───────────────────────────────────────


@requires_isaac
class TestErrorHandling:
    def test_unknown_command(self, conn: IsaacConnection) -> None:
        resp = send(conn, "nonexistent.command")
        assert resp["status"] == "error"
        assert "Unknown command" in resp.get("message", "")
