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

"""Substring checks on MCP tool docstrings and the server instruction block."""

import os

TOOLS_DIR = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "tools")
SERVER_PY = os.path.join(os.path.dirname(__file__), "..", "isaac_mcp", "server.py")


def _read_tool_source(filename):
    with open(os.path.join(TOOLS_DIR, filename)) as f:
        return f.read()


def _read_server_source():
    with open(SERVER_PY) as f:
        return f.read()


def test_create_object_documents_scale_multiplier():
    src = _read_tool_source("objects.py")
    # scale= is a raw multiplier of the primitive's native size
    assert "native size" in src
    assert "2 m" in src or "2m" in src  # native size of Cube/Sphere/etc
    assert "scale=0.5" in src  # worked example -> 1 m
    assert "size=" in src  # steer to size= for absolute meters


def test_step_simulation_docstring_forbids_play_first():
    src = _read_tool_source("simulation.py")
    assert "Do NOT call play_simulation" in src
    assert "frozen" in src


def test_get_simulation_state_drops_verify_running_claim():
    src = _read_tool_source("simulation.py")
    assert "verify the simulation is running before" not in src


def test_server_instructions_debug_loop_is_step_only():
    src = _read_server_source()
    assert "step-only" in src
    assert "never play" in src.lower() or "do not call play_simulation" in src.lower()


def test_stop_simulation_documents_reset():
    src = _read_tool_source("simulation.py")
    assert "spawn pose" in src
    assert "reset" in src.lower()


def test_reload_script_documents_scriptnode_mode():
    src = _read_tool_source("simulation.py")
    assert "ScriptNode" in src
    assert "recompile" in src.lower()


def test_get_isaac_logs_has_since_last_play_and_nondestructive_default():
    import ast

    src = _read_tool_source("simulation.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_isaac_logs":
            defaults = {a.arg: d for a, d in zip(node.args.args[-len(node.args.defaults) :], node.args.defaults)}
            assert "since_last_play" in {a.arg for a in node.args.args}
            # clear defaults to False (non-destructive)
            clear_default = defaults.get("clear")
            assert isinstance(clear_default, ast.Constant) and clear_default.value is False
            return
    raise AssertionError("get_isaac_logs tool not found")


def test_create_action_graph_has_inline_script_param():
    import ast

    src = _read_tool_source("graphs.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "create_action_graph":
            arg_names = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
            assert "inline_script" in arg_names
            assert "script_file" in src and "recommended" in src.lower()
            return
    raise AssertionError("create_action_graph tool not found")


def test_execute_script_warns_about_live_graph():
    src = _read_tool_source("simulation.py")
    assert "ScriptNode" in src
    assert "silently" in src.lower()
    assert "stop" in src.lower()


def test_server_instructions_cover_contracts():
    src = _read_server_source()
    assert "resets to spawn" in src.lower() or "spawn state" in src.lower()  # stop (#8)
    assert "[PRINT]" in src  # log capture (#5)
    assert "silently" in src.lower()  # execute_script (#6)
    assert "silent" in src.lower()  # ScriptNode write failures


def test_server_instructions_warn_about_the_newton_engine():
    """Newton is beta and has two faults the agent cannot detect from a response.

    Drives do not converge (#21), and a joint with no articulation root aborts
    Newton's model build for the whole session -- every later physics command
    fails and neither deleting the prim nor clear_scene recovers it (measured:
    an empty stage, 0 prims, still failed). Only a restart does.

    execute_script is the only path that can author such a joint, so it is named
    specifically. import_urdf is NOT: measured on 6.0.1 Newton, the importer
    applies ArticulationRootAPI itself (/World/twolink/Geometry/base_link) and
    the import leaves physics healthy, so warning about it there would be false.

    Keep this short. It is read by every agent on every session; it carries what
    to do, not why.
    """
    src = _read_server_source()
    assert "newton" in src.lower(), "the instruction block never mentions the engine at all"
    assert "get_simulation_state reports `engine`" in src
    assert "absent on 5.1" in src, "5.1 has no engine key; saying otherwise sends agents looking for it"
    assert "do not converge" in src
    assert "ArticulationRootAPI" in src
    assert "restarting Isaac Sim" in src


def test_the_engine_guidance_stays_short():
    """A contract doc that explains mechanism stops being read."""
    src = _read_server_source()
    block = src[src.index("### Physics engine") : src.index("### Physics engine") + 800]
    block = block.split('"""')[0]
    assert len(block.splitlines()) <= 9, f"engine guidance grew to {len(block.splitlines())} lines"


def _tool_docstring(filename, func):
    """The docstring of one tool function, so a check cannot be satisfied by
    matching text somewhere else in the module."""
    import ast

    tree = ast.parse(_read_tool_source(filename))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            return ast.get_docstring(node) or ""
    raise AssertionError(f"{func} not found in {filename}")


def test_scene_setup_instructions_put_load_environment_before_create_physics_scene():
    """#37's guard only holds in one order, and the setup block prescribed the other.

    create_physics_scene skips its own ground plane when the stage already has
    a collision floor — but it checks once, when it runs. Called before
    load_environment, the environment's floor lands afterwards and the stage
    carries two. Measured on 6.0.1 PhysX, 6.0.1 Newton and 5.1.0: two collision
    Planes reversed, one in the documented order.

    The Scene Setup line never mentioned load_environment at all, so an agent
    following it literally hit the stacking case every time.
    """
    src = _read_server_source()
    setup = src.split("### Scene Setup")[1].split("###")[0]

    assert "load_environment" in setup, "the setup order must say where load_environment goes"
    assert setup.index("load_environment") < setup.index("create_physics_scene"), (
        "load_environment must come before create_physics_scene, or the stage ends up with two floors"
    )


def test_create_physics_scene_docstring_qualifies_the_no_second_floor_claim():
    """The docstring stated the guarantee unconditionally; it holds in one order only."""
    doc = _tool_docstring("scene.py", "create_physics_scene")

    assert "load_environment" in doc, "the claim depends on load_environment running first — say so"
    assert "before" in doc.lower()


# ── the instruction budget ───────────────────────────────────────────────────

# Every tool docstring is in the agent's context on EVERY call, so the block of
# them is a standing cost paid per request, not per use of that tool. Each fix
# to this server has added a paragraph explaining what went wrong, and the
# explanations came to outweigh the instructions: 23,350 characters across the
# tool docstrings (~5.8k tokens) before this budget existed, trimmed to 19,730
# (~4.9k) by moving rationale out without dropping any contract.
#
# That dilutes the lines an agent must actually act on. Rationale belongs in
# code comments and commit messages, which cost the agent nothing; docstrings
# carry the contract -- fields returned, ordering rules, actionable limits.
#
# These are ratchets. Lower them when a docstring gets tighter; raising one is
# a decision to spend context, and should be argued for in the commit.
MAX_TOOL_DOCSTRING_CHARS = 19800
MAX_SINGLE_DOCSTRING_LINES = 24


def _tool_docstrings():
    import ast
    import glob

    out = {}
    for path in sorted(glob.glob(os.path.join(TOOLS_DIR, "*.py"))):
        with open(path) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                doc = ast.get_docstring(node)
                if doc:
                    out["%s:%s" % (os.path.basename(path), node.name)] = doc
    return out


def test_tool_docstrings_stay_within_the_instruction_budget():
    docs = _tool_docstrings()
    total = sum(len(d) for d in docs.values())

    assert total <= MAX_TOOL_DOCSTRING_CHARS, (
        "tool docstrings total %d chars (~%dk tokens), over the %d budget — "
        "move rationale into code comments and keep the contract" % (total, total // 1000, MAX_TOOL_DOCSTRING_CHARS)
    )


def test_no_single_tool_docstring_dominates_the_budget():
    docs = _tool_docstrings()
    oversized = {k: len(v.splitlines()) for k, v in docs.items() if len(v.splitlines()) > MAX_SINGLE_DOCSTRING_LINES}

    assert not oversized, (
        "these docstrings are longer than %d lines: %s — an agent skims them, "
        "and the actionable line gets lost in the explanation"
        % (MAX_SINGLE_DOCSTRING_LINES, ", ".join("%s (%d)" % (k, v) for k, v in sorted(oversized.items())))
    )
