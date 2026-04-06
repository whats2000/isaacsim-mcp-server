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
4. get_prim_info — verify positions and actual sizes

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
