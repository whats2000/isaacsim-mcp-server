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
