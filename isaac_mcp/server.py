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

"""Isaac Sim MCP Server — entry point.

Registers all tools from tools/ submodules and starts the FastMCP server.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from mcp.server.fastmcp import FastMCP

from isaac_mcp.connection import get_isaac_connection, reset_isaac_connection
from isaac_mcp.tools import register_all_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("IsaacMCPServer")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle."""
    try:
        logger.info("IsaacMCP server starting up")
        try:
            get_isaac_connection()
            logger.info("Successfully connected to Isaac on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Isaac on startup: {e}")
        yield {}
    finally:
        reset_isaac_connection()
        logger.info("IsaacMCP server shut down")


_INSTRUCTIONS = """\
Isaac Sim integration through the Model Context Protocol.

## MCP Tools vs Scripts / Action Graphs

MCP tools operate BETWEEN frames (editor-level): scene setup, inspection, stepping, joint control, diagnostics.
Scripts/Action Graphs operate WITHIN frames (runtime-level): control loops, IK, state machines.

## Workflow

### Scene Setup
1. get_scene_info → 2. load_environment (if using one) → 3. create_physics_scene → 4. create_robot / create_object → 5. get_prim_info (verify sizes)
- load_environment goes BEFORE create_physics_scene. An environment brings its own collision floor,
  and create_physics_scene skips adding a second one only if that floor is already on the stage — it
  checks once, when it runs. The reverse order leaves two floors and the engine decides which wins;
  load_environment reports it as collision_floor_warning.
- create_robot: call list_available_robots first for exact keys (lowercase, no spaces, e.g. "frankafr3")
- Always get_prim_info to query actual positions/sizes BEFORE writing controller scripts

### Debug Loop (step-only — never play)
The debug loop is step-only: set_joint_positions + step_simulation with
observe_prims/observe_joints on a FROZEN timeline. Do NOT call play_simulation
while debugging — step errors if the timeline is already playing. If issues:
get_joint_config, get_physics_state, get_isaac_logs.
play_simulation is ONLY for a final continuous run / ScriptNode demo.
Two separate debug modes: MCP loop = step on a frozen timeline (no graph);
ScriptNode/Action-Graph = play + get_isaac_logs (graphs tick only while playing
and cannot be stepped). Do not mix them.

### Controller Development
Write .py file → reload_script → step_simulation to debug → edit & reload →
play_simulation only for the final continuous run.

### ScriptNode (Action Graph)
create_action_graph(script_file="/path/to/controller.py") wires OnPlaybackTick → ScriptNode.

**ScriptNode rules:**
1. MUST define setup(db) and compute(db) — never use legacy mode (no compute = broken exec scoping)
2. Use module-level globals + `global` keyword in compute() for persistent state
3. Subscribe to timeline STOP event to reset state (or Stop→Play leaves stale objects)
4. WARMUP pattern: skip ~30 frames in compute() before calling World.initialize_physics() + robot.initialize()
5. ScriptNode fires once during create_action_graph — objects created then go stale at Play

See demo/franka_pick_place.py for a complete working example.

### Tool Priority
Prefer named tools over execute_script: get_joint_positions, get_prim_info, get_physics_state,
get_joint_config, get_isaac_logs, create_action_graph, edit_action_graph.

### Contracts (silent-failure map)
- step_simulation is authoritative and freezes the timeline; it errors if the
  timeline is already playing. Never play during the debug loop (see Debug Loop).
- stop_simulation resets the scene to spawn state (state at first Play).
- get_isaac_logs shows carb.log_*/omni.log WARN+ERROR plus captured stdout
  tagged [PRINT]; plain print() outside execute_script/reload_script may not
  appear. Defaults are non-destructive and scoped to the current run.
- execute_script can silently disturb a live Action Graph / ScriptNode that
  controls the same articulation — stop the graph first.
- ScriptNode physics contract: physics must be initialised before articulation
  writes take effect; such write failures are SILENT (not raised). Follow the
  WARMUP pattern (skip ~30 frames, then World.initialize_physics() +
  robot.initialize()).

### Physics engine (Isaac Sim 6.0)
get_simulation_state reports `engine` on 6.0; absent on 5.1, which is PhysX.
On "newton" (beta): joint drives do not converge and joint limits are not
enforced — run motion work on PhysX (isaac-sim.sh). Never author a joint via
execute_script unless an ancestor has UsdPhysics.ArticulationRootAPI: it aborts
physics for the whole session and only restarting Isaac Sim recovers it.
"""

mcp = FastMCP(
    "IsaacSimMCP",
    instructions=_INSTRUCTIONS,
    lifespan=server_lifespan,
)

register_all_tools(mcp, get_isaac_connection)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
