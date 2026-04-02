# Isaac Sim MCP

[![PyPI version](https://img.shields.io/pypi/v/isaacsim-mcp-server)](https://pypi.org/project/isaacsim-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Quality](https://archestra.ai/mcp-catalog/api/badge/quality/whats2000/isaacsim-mcp-server)](https://archestra.ai/mcp-catalog/api/badge/quality/whats2000/isaacsim-mcp-server)

Natural language control for NVIDIA Isaac Sim through the Model Context Protocol (MCP).

This project connects an MCP server to an Isaac Sim extension so any MCP-compatible IDE or client can inspect scenes, create robots and assets, control simulation, and execute targeted Python inside Isaac Sim from plain-English prompts.

![Robot Party Demo](media/add_more_robot_into_party.gif)

## Why This Project

- Built for NVIDIA Isaac Sim `5.1.0`
- Clean split between MCP server tools and in-sim extension handlers
- `39` tools across `8` categories for scene, robot, sensor, asset, and simulation workflows
- Modular adapter-based architecture designed to isolate Isaac Sim version-specific APIs
- Works well for rapid scene prototyping, robotics demos, asset loading, and agent-driven simulation workflows

## What's New For Isaac Sim 5.1.0

The current codebase is organized around Isaac Sim `5.1.0` and its `isaacsim.*` API surface.

- Version-specific Isaac Sim calls are routed through `isaac_sim_mcp_extension/adapters/v5.py`
- Socket commands use a modular category/action layout such as `scene.get_info` and `robots.create`
- Tools are grouped by domain so the MCP server and extension stay easier to extend and test
- Robot and environment discovery are designed to reflect the assets available in your active Isaac Sim setup

## Architecture

```text
MCP Client (Cursor, VS Code, Claude Code, etc.)
        |
        v
isaac_mcp/server.py
        |
        v
TCP socket (default: localhost:8766)
        |
        v
isaac.sim.mcp_extension
        |
        v
Handlers -> Adapter -> Isaac Sim 5.1.0 APIs
```

## Requirements

- NVIDIA Isaac Sim `5.1.0`
- Python `3.10+`
- `uv` / `uvx`
- `mcp[cli]`
- An MCP-compatible client (Cursor, VS Code, Claude Code, Windsurf, JetBrains IDEs, etc.)

## Quick Start

### 1. Clone the repo

```bash
mkdir -p ~/Documents/GitHub
cd ~/Documents/GitHub
git clone https://github.com/whats2000/isaacsim-mcp-server
cd ~/Documents/GitHub/isaacsim-mcp-server
```

### Alternative: Install from PyPI

```bash
pip install isaacsim-mcp-server
```

This installs the MCP server only. You still need Isaac Sim with the extension running (see steps 3-4 below).

### 2. Set up Python once

```bash
./scripts/setup_python_env.sh
```

### 3. Launch Isaac Sim with the extension enabled

Optional environment variables for Beaver3D and NVIDIA-backed asset workflows:

```bash
export BEAVER3D_MODEL="<your beaver3d model name>"
export ARK_API_KEY="<your beaver3d api key>"
export NVIDIA_API_KEY="<your nvidia api key>"
```

```bash
./scripts/run_isaac_sim.sh
```

Expected startup logs should include lines similar to:

```text
[ext: isaac.sim.mcp_extension-0.3.0] startup
trigger  on_startup for:  isaac.sim.mcp_extension-0.3.0
Registered 40 command handlers
Isaac Sim MCP server started on localhost:8766
```

### 4. Run the MCP server

This script is the command your MCP client should launch:

```bash
./scripts/run_mcp_server.sh
```

### 5. Add the MCP server to your IDE

Replace `/absolute/path/to/isaacsim-mcp-server` with your actual repo path in the examples below.

#### Cursor

Open **Cursor Settings > MCP** and add a new global MCP server, or edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

#### VS Code (Claude Code Extension)

Create or edit `.vscode/mcp.json` in your workspace root:

```json
{
  "servers": {
    "isaac-sim": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

Alternatively, add it to your User or Workspace `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "isaac-sim": {
        "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
      }
    }
  }
}
```

#### Claude Code (CLI)

Add the server using the CLI:

```bash
claude mcp add isaac-sim /absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh
```

Or manually edit `~/.claude.json` (global) or `.mcp.json` (project-level):

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

#### Claude Desktop

Edit the config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

#### Windsurf

Open **Windsurf Settings > MCP** or edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

#### JetBrains IDEs (IntelliJ, PyCharm, etc.)

JetBrains IDEs with MCP support read from a `mcpServers` block in their settings. Go to **Settings > Tools > AI Assistant > MCP Servers**, or add the server configuration manually. Refer to the [JetBrains MCP documentation](https://www.jetbrains.com/help/idea/model-context-protocol.html) for your specific IDE version.

### Multiple Instances

You can run multiple Isaac Sim sessions side by side. Each instance uses a different port — the launcher auto-assigns a free port starting from `8766`. To control each instance from your MCP client, add a separate server entry per instance with the `ISAAC_MCP_PORT` environment variable.

#### Claude Code (CLI)

```bash
# First instance (default port 8766)
claude mcp add isaac-sim /absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh

# Second instance (port 8767)
claude mcp add isaac-sim-2 -e ISAAC_MCP_PORT=8767 -- /absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh
```

#### Cursor / Claude Desktop / Windsurf

Add multiple entries to your MCP config, each with a different `ISAAC_MCP_PORT`:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    },
    "isaac-sim-2": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh",
      "env": {
        "ISAAC_MCP_PORT": "8767"
      }
    }
  }
}
```

#### VS Code (Claude Code Extension)

```json
{
  "servers": {
    "isaac-sim": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    },
    "isaac-sim-2": {
      "command": "/absolute/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh",
      "env": {
        "ISAAC_MCP_PORT": "8767"
      }
    }
  }
}
```

The port each Isaac Sim instance uses is printed in the terminal when launched and logged to `logs/mcp_server_<port>.log`.

## Desktop Launcher (Linux)

You can install a separate **Isaac Sim MCP** application icon alongside the original Isaac Sim launcher.

```bash
./scripts/install_desktop_entry.sh
```

This gives you two application icons:
- **Isaac Sim** — original, unchanged
- **Isaac Sim MCP** — launches with the MCP extension and server

The MCP launcher will:
- Auto-assign a free port (starting from 8766) so multiple instances can run side by side
- Wait for the extension socket to be ready before starting the MCP server
- Automatically stop the MCP server when Isaac Sim exits

MCP server logs are written to `logs/mcp_server_<port>.log`.

To uninstall:

```bash
rm ~/.local/share/applications/IsaacSimMCP.desktop
```

## Setup Notes

These are the simple scripts used above:

```bash
./scripts/setup_python_env.sh
./scripts/run_isaac_sim.sh
./scripts/run_mcp_server.sh
./scripts/launch_isaac_sim_mcp.sh    # combined launcher (Isaac Sim + MCP server)
./scripts/install_desktop_entry.sh   # install desktop shortcut
```

By default:
- `setup_python_env.sh` uses `/usr/bin/python3.10`
- `run_isaac_sim.sh` uses `$HOME/isaacsim/isaac-sim.sh`
- `run_mcp_server.sh` uses `.venv/bin/python`

You can override them when needed:

```bash
PYTHON_SPEC=3.11 ./scripts/setup_python_env.sh
ISAACSIM_ROOT=/path/to/isaacsim ./scripts/run_isaac_sim.sh
```

If Isaac Sim says `Can't find extension with name: isaac.sim.mcp_extension`, verify you are in the repo root and the manifest exists:

```bash
pwd
test -f ./isaac.sim.mcp_extension/config/extension.toml && echo OK
```

Verified on this repo:
- `./scripts/run_isaac_sim.sh` works
- `./scripts/run_mcp_server.sh` resolves the correct local `.venv`
- `--ext-folder <repo-root>` with `--enable isaac.sim.mcp_extension` works
- `--ext-folder <repo-root>/isaac.sim.mcp_extension` does not work
- `--enable isaac_sim_mcp_extension` does not work

## Recommended Workflow

When prompting your MCP-enabled IDE or client:

1. Start with `get_scene_info`
2. Create a physics scene if the stage is empty
3. Prefer purpose-built tools before using `execute_script`
4. Use `list_available_robots` or `list_environments` before fuzzy-matched loading
5. Use `play_simulation`, `pause_simulation`, `stop_simulation`, and `step_simulation` explicitly when timing matters
6. Use `get_simulation_state` to check timeline state and physics dt before stepping
7. Use `get_joint_config` and `get_physics_state` to debug joint drives and rigid body issues
8. Use `reload_script` to hot-patch controller code without restarting the simulation
9. Use `step_simulation` with `observe_prims` and `observe_joints` for step-and-observe debugging loops

## Example Prompts

### Scene bootstrap

```text
Check the connection with get_scene_info.
If the scene is empty, create a physics scene.
Add stronger lighting and place a camera that looks at the workspace.
```

### Robot layout

```text
Check the scene first.
Create three Franka robots in a row at [0, 0, 0], [2, 0, 0], and [4, 0, 0].
Then add a Go1 robot at [1, 3, 0].
```

### Environment loading

```text
List available environments, choose a warehouse-like one, and load it at /Environment.
After that, create a camera and capture an image.
```

### Asset search

```text
Search for a rusty desk, load the best USD result near [0, 5, 0], and scale it to [2, 2, 2].
```

### 3D generation

```text
Generate a 3D model from this image URL and place it at [3, 0, 0] with scale [2, 2, 2].
```

## Tool Overview

The MCP server currently exposes `39` tools across `8` categories.

| Category | Tools | Highlights |
| --- | ---: | --- |
| Scene | 7 | scene info, physics scene creation, prim inspection, environment discovery/loading |
| Objects | 4 | create, delete, transform, clone primitives |
| Lighting | 2 | create and tune lights |
| Robots | 6 | create robots, inspect joints, refresh library, command articulations |
| Sensors | 4 | camera and lidar creation plus capture / point cloud access |
| Materials | 2 | create and apply materials |
| Assets | 4 | URDF import, USD load/search, Beaver3D generation |
| Simulation | 10 | play, pause, stop, step+observe, set physics, execute Python with stdout capture, simulation state, physics inspection, joint config, hot-reload |

### Scene

- `get_scene_info`
- `create_physics_scene`
- `clear_scene`
- `list_prims`
- `get_prim_info`
- `list_environments`
- `load_environment`

### Objects

- `create_object`
- `delete_object`
- `transform_object`
- `clone_object`

### Lighting

- `create_light`
- `modify_light`

### Robots

- `create_robot`
- `list_available_robots`
- `refresh_robot_library`
- `get_robot_info`
- `set_joint_positions`
- `get_joint_positions`

### Sensors

- `create_camera`
- `capture_image`
- `create_lidar`
- `get_lidar_point_cloud`

### Materials

- `create_material`
- `apply_material`

### Assets

- `import_urdf`
- `load_usd`
- `search_usd`
- `generate_3d`

### Simulation

- `play_simulation`
- `pause_simulation`
- `stop_simulation`
- `step_simulation` — supports `observe_prims` and `observe_joints` for step-and-observe workflows
- `set_physics_params`
- `execute_script` — captures `stdout`/`stderr`, supports `cwd` for module path setup
- `get_simulation_state` — timeline state (playing/paused/stopped), current time, physics dt
- `get_physics_state` — rigid body status, mass, velocities, kinematic flag, collision info
- `get_joint_config` — joint drive stiffness, damping, limits, runtime target vs actual position, position error
- `reload_script` — hot-reload Python modules or execute script files with auto `sys.path` setup

## Demo: Franka Pick-and-Place

The repo includes a ready-to-run pick-and-place demo at `demo/franka_pick_place.py`. It uses RMPflow for motion planning and runs as an OmniGraph ScriptNode so you can press Play/Stop to run and rerun.

```text
Ask the AI to set up the scene:

1. Create a physics scene, ground plane, and a Franka FR3 robot
2. Add two tables and a small cube on the first table
3. Wire the pick-and-place script into an Action Graph
4. Press Play — the robot picks the cube and places it on the second table
```

The demo showcases the observability tools for debugging:
- `get_joint_config` to inspect drive stiffness and position error
- `step_simulation` with `observe_prims` to track the cube during motion
- `get_physics_state` to verify rigid body and collision setup
- `reload_script` to iterate on the controller without restarting

## Development

Run the MCP inspector during development:

```bash
./.venv/bin/python -m mcp dev ./isaac_mcp/server.py
```

The inspector is typically available at `http://localhost:5173`.

## Demo Media

- [Robot Party Demo (MP4)](media/add_more_robot_into_party.mp4)

## Contributing

Pull requests are welcome. Small improvements to tools, docs, adapters, and tests are all useful.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
