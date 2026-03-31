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

"""Test the IsaacConnection module structure."""

import ast
import os


def test_connection_module_exists():
    path = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "connection.py")
    assert os.path.exists(path)


def test_connection_has_required_classes_and_functions():
    path = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "connection.py")
    with open(path) as f:
        tree = ast.parse(f.read())
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "IsaacConnection" in class_names
    assert "get_isaac_connection" in func_names
    # Check IsaacConnection has send_command method
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IsaacConnection":
            methods = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
            assert "connect" in methods
            assert "disconnect" in methods
            assert "send_command" in methods
