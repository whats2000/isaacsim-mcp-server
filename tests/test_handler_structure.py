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

"""Validate that the adapter and handler structure is correct."""

import ast
import os

EXTENSION_ROOT = os.path.join(os.path.dirname(__file__), "..", "isaac.sim.mcp_extension", "isaac_sim_mcp_extension")


def _parse_file(path):
    with open(path) as f:
        return ast.parse(f.read())


def test_adapter_base_has_all_abstract_methods():
    """Verify the base adapter defines all required abstract methods."""
    tree = _parse_file(os.path.join(EXTENSION_ROOT, "adapters", "base.py"))
    methods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name != "__init__":
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                    methods.add(node.name)
                elif isinstance(decorator, ast.Attribute) and decorator.attr == "abstractmethod":
                    methods.add(node.name)
    expected = {
        "get_stage",
        "get_assets_root_path",
        "discover_environments",
        "load_environment",
        "create_prim",
        "delete_prim",
        "add_reference_to_stage",
        "set_prim_transform",
        "get_prim_transform",
        "list_prims",
        "get_prim_info",
        "create_xform_prim",
        "create_articulation",
        "discover_robots",
        "get_robot_joint_info",
        "set_joint_positions",
        "get_joint_positions",
        "create_world",
        "create_simulation_context",
        "create_physics_scene",
        "create_camera",
        "capture_camera_image",
        "create_lidar",
        "get_lidar_point_cloud",
        "create_pbr_material",
        "create_physics_material",
        "apply_material",
        "create_light",
        "modify_light",
        "clone_prim",
        "import_urdf",
        "play",
        "pause",
        "stop",
        "step",
        "execute_script",
        # Observability methods (issue #1)
        "get_simulation_state",
        "get_physics_state",
        "get_joint_config",
        "reload_script",
        # Dimensional data (issue #2)
        "get_prim_actual_size",
    }
    assert methods == expected, f"Missing: {expected - methods}, Extra: {methods - expected}"


def test_v5_adapter_implements_all_methods():
    """Verify v5 adapter implements every abstract method from base."""
    base_tree = _parse_file(os.path.join(EXTENSION_ROOT, "adapters", "base.py"))
    v5_tree = _parse_file(os.path.join(EXTENSION_ROOT, "adapters", "v5.py"))

    base_methods = set()
    for node in ast.walk(base_tree):
        if isinstance(node, ast.FunctionDef) and node.name != "__init__":
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Name) and decorator.id == "abstractmethod") or (
                    isinstance(decorator, ast.Attribute) and decorator.attr == "abstractmethod"
                ):
                    base_methods.add(node.name)

    v5_methods = set()
    for node in ast.walk(v5_tree):
        if isinstance(node, ast.FunctionDef):
            v5_methods.add(node.name)

    missing = base_methods - v5_methods
    assert not missing, f"v5 adapter missing implementations: {missing}"


def test_all_handler_modules_have_register():
    """Verify every handler module exposes a register(registry, adapter) function."""
    handlers_dir = os.path.join(EXTENSION_ROOT, "handlers")
    handler_files = [
        "scene.py",
        "objects.py",
        "lighting.py",
        "robots.py",
        "sensors.py",
        "materials.py",
        "assets.py",
        "simulation.py",
    ]
    for filename in handler_files:
        filepath = os.path.join(handlers_dir, filename)
        assert os.path.exists(filepath), f"Handler file missing: {filename}"
        tree = _parse_file(filepath)
        func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert "register" in func_names, f"{filename} missing register() function"
