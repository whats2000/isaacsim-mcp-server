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

"""Both adapters must route prim transforms through the shared helper.

The rotation bug was that ``set_prim_transform`` only ever wrote
``xformOp:rotateXYZ``, so on a prim carrying ``xformOp:orient`` the requested
rotation composed with the existing one and landed after ``xformOp:scale``.
Measured live on a prim with orient=90 deg and scale=(1,2,1): asking for 45 deg
gave 135 deg and shear 1.5, identically on 5.1.0 and 6.0.1.

These are structural checks -- the real behaviour needs a USD runtime and is
covered by the live harness -- but they stop either adapter drifting back to
hand-rolled op handling, which is how the two copies diverged before.
"""

import ast
import os

ADAPTERS = os.path.join(
    os.path.dirname(__file__), "..", "isaac.sim.mcp_extension", "isaac_sim_mcp_extension", "adapters"
)


def _func(filename, name):
    path = os.path.join(ADAPTERS, filename)
    with open(path) as f:
        src = f.read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found in {filename}")


def test_both_adapters_write_transforms_through_the_helper():
    for filename in ("v5.py", "v6.py"):
        body = _func(filename, "set_prim_transform")
        assert "set_transform(" in body, f"{filename} does not use the shared writer"
        assert "AddRotateXYZOp" not in body, f"{filename} still hand-rolls the rotate op"


def test_both_adapters_read_transforms_through_the_helper():
    for filename in ("v5.py", "v6.py"):
        body = _func(filename, "get_prim_transform")
        assert "read_transform(" in body, f"{filename} does not use the shared reader"


def test_reader_reports_rotation_and_scale_not_just_position():
    """get_prim_info used to return position only, so rotation was unanswerable."""
    path = os.path.join(ADAPTERS, "transforms.py")
    with open(path) as f:
        src = f.read()
    body = _func("transforms.py", "read_transform")
    # There is deliberately no bare "position": naming one frame and not the
    # other is what made a parent-relative value read as a world one (#39).
    for key in ('"position_local"', '"position_world"', '"rotation"', '"scale"', '"rotation_units"'):
        assert key in body, f"read_transform does not report {key}"
    # Scale must not be allowed to corrupt the reported rotation.
    assert "Orthonormalize" in body
    assert "def set_transform" in src


def test_writer_prefers_the_op_the_prim_already_uses():
    body = _func("transforms.py", "set_transform")
    assert "xformOp:orient" in body, "writer ignores quaternion orientation"
    assert "_insert_before_scale" in body, "a newly added rotate op would append after scale"


def test_tool_docstring_documents_rotation():
    """The docstring advertised position and size only; agents read that."""
    tools = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "tools", "scene.py")
    with open(tools) as f:
        src = f.read()
    assert "rotation" in src
    assert "degrees" in src
