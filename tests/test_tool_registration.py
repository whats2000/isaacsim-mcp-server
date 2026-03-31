# MIT License
#
# Copyright (c) 2023-2025 omni-mcp
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
