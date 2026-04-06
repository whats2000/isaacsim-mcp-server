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

MCP tools operate BETWEEN simulation frames (editor-level):
- Scene setup: create_physics_scene, create_object, create_robot, load_environment
- Inspection: get_prim_info, get_robot_info, get_physics_state, get_joint_config
- Stepping: step_simulation (advance N frames and observe state)
- Joint control: set_joint_positions, get_joint_positions
- Diagnostics: get_isaac_logs, get_simulation_state

Scripts and Action Graphs operate WITHIN simulation frames (runtime-level):
- Real-time control loops and physics callbacks
- IK solvers, trajectory planners, state machines
- Sensor data processing pipelines
Use execute_script for one-off setup, or write a .py file and load it with reload_script.
Use create_action_graph to build Action Graphs programmatically (OnPlaybackTick → ScriptNode etc.).

## Workflow

### Scene Setup
1. get_scene_info — verify connection
2. create_physics_scene — physics + ground plane
3. create_robot / create_object / load_environment — populate scene
   - create_robot uses fuzzy matching: call list_available_robots first to get exact keys
   - Robot keys are lowercase, no spaces (e.g. "frankafr3", not "franka fr3")
4. get_prim_info — verify positions and actual sizes BEFORE writing controller scripts

### Debug Loop (step-and-observe)
1. set_joint_positions — command the robot
2. step_simulation with observe_prims and observe_joints — advance and read state
3. If drives misbehave → get_joint_config (check stiffness, damping, position error)
4. If objects misbehave → get_physics_state (check collision, mass, rigid body)
5. If anything errors → get_isaac_logs
6. Adjust and repeat

Do NOT use play_simulation + sleep + execute_script as a debug loop.
Use step_simulation for controlled, observable stepping.

### Controller Development
1. Write controller as a .py file (state machine, IK, physics callbacks)
2. reload_script to load it into Isaac Sim
3. step_simulation to debug the behavior step-by-step
4. Edit the file, reload_script again to iterate
5. play_simulation once the controller works correctly

### ScriptNode with File-Based Scripts
For controllers that run every tick via Action Graph ScriptNode:

**One-step** (recommended): use script_file parameter:
  create_action_graph(script_file="/path/to/controller.py")

**Two-step** (manual): create graph, then attach script file:
  1. create_action_graph with OnPlaybackTick → ScriptNode nodes
  2. edit_action_graph to set ScriptNode.inputs:usePath=true and ScriptNode.inputs:scriptPath

To reload after editing, call edit_action_graph with the same scriptPath — it auto-resets
state:omni_initialized to force the ScriptNode to re-read the file.

**IMPORTANT**: The ScriptNode fires ONCE during create_action_graph (before Play starts).
Any objects initialised then (robot, World) become stale when Play begins. Scripts must
handle re-initialisation — see the WARMUP pattern below.

### CRITICAL: ScriptNode Script Patterns

ScriptNode scripts MUST define `setup(db)` and/or `compute(db)` functions.
This is the "proper" mode where module-level globals, function definitions,
and list comprehensions all work correctly.

**DO NOT use "legacy mode"** (no compute(db) function). Legacy mode runs the
entire script via exec() each tick with severe scoping issues:
- Variables go into compute() locals, LOST every tick
- Function defs and list comprehensions can't access exec locals
- State must be stored in builtins (fragile and error-prone)
Always define setup(db) and compute(db).

**Recommended structure:**
```python
import numpy as np
import omni.timeline

# Module-level globals for persistent state
_robot = None
_state = "IDLE"
_tl_sub = None
_world = None

def _on_tl(event):
    # ESSENTIAL: Reset state on STOP so next Play re-initialises cleanly.
    # Without this, pressing Stop → Play leaves stale robot/World objects.
    global _robot, _state, _world
    if event.type == int(omni.timeline.TimelineEventType.STOP):
        _robot = None
        _state = "IDLE"
        if _world is not None:
            _world.clear_instance()
            _world = None

def setup(db=None):
    # Runs once on first evaluation. Subscribe to timeline STOP.
    global _tl_sub
    if _tl_sub is None:
        tl = omni.timeline.get_timeline_interface()
        _tl_sub = tl.get_timeline_event_stream().create_subscription_to_pop(_on_tl)

def compute(db=None):
    # Runs every tick. Use global keyword for mutable state.
    global _robot, _state, _world
    ...
    return True
```

**Physics initialisation — WARMUP pattern**: `SingleArticulation.initialize()`
requires `World.physics_sim_view` to be non-None. When the user presses Play
from the Isaac Sim UI, physics needs a few frames to settle before the tensor
API is available. Use a WARMUP state that skips the first ~30 frames, then
creates a World and calls `initialize_physics()`:
```python
WARMUP_FRAMES = 30

def compute(db=None):
    global _state, _frame, _world, _robot
    if _state == "WARMUP":
        _frame += 1
        if _frame >= WARMUP_FRAMES:
            from isaacsim.core.api import World
            _world = World.instance()
            if _world is None:
                _world = World(physics_dt=1/60.0, stage_units_in_meters=1.0)
            _world.initialize_physics()
            # Now SingleArticulation.initialize() will work
            from isaacsim.core.prims import SingleArticulation
            _robot = SingleArticulation(prim_path="/World/MyRobot", name="my_robot")
            _robot.initialize()
            _state = "RUNNING"
        return True
    # ... rest of controller logic
```
The adapter's create_action_graph() and play() also call _ensure_physics_world()
which helps when using MCP tools, but the WARMUP pattern is essential for UI Play.


### Tool Priority
Always prefer named tools over execute_script:
- Reading joints → get_joint_positions (not execute_script)
- Inspecting prims → get_prim_info (not execute_script)
- Checking physics → get_physics_state (not execute_script)
- Checking drives → get_joint_config (not execute_script)
- Checking logs → get_isaac_logs (not execute_script)
- Building Action Graphs → create_action_graph (not execute_script)
- Editing Action Graphs (update script, set usePath/scriptPath) → edit_action_graph

execute_script is the escape hatch for operations no named tool covers.
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
