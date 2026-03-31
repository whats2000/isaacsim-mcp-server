"""Test that all tool modules have correct structure."""

import ast
import os

TOOLS_DIR = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "tools")

EXPECTED_MODULES = [
    "scene.py", "objects.py", "lighting.py", "robots.py",
    "sensors.py", "materials.py", "assets.py", "simulation.py",
]


def test_all_tool_modules_exist():
    for filename in EXPECTED_MODULES:
        path = os.path.join(TOOLS_DIR, filename)
        assert os.path.exists(path), f"Missing tool module: {filename}"


def test_all_tool_modules_have_register_tools():
    for filename in EXPECTED_MODULES:
        path = os.path.join(TOOLS_DIR, filename)
        with open(path) as f:
            tree = ast.parse(f.read())
        func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert "register_tools" in func_names, f"{filename} missing register_tools() function"


def test_init_imports_all_modules():
    path = os.path.join(TOOLS_DIR, "__init__.py")
    with open(path) as f:
        content = f.read()
    for module_name in ["scene", "objects", "lighting", "robots", "sensors", "materials", "assets", "simulation"]:
        assert module_name in content, f"tools/__init__.py missing import of {module_name}"
