# Isaac Sim MCP Server

[![PyPI version](https://img.shields.io/pypi/v/isaacsim-mcp-server)](https://pypi.org/project/isaacsim-mcp-server/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Quality](https://archestra.ai/mcp-catalog/api/badge/quality/whats2000/isaacsim-mcp-server)](https://archestra.ai/mcp-catalog/api/badge/quality/whats2000/isaacsim-mcp-server)

> Natural language control for NVIDIA Isaac Sim through the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP).

Connect any MCP-compatible IDE (Cursor, VS Code, Claude Code, Windsurf, JetBrains) to a running Isaac Sim instance and control it with plain-English prompts -- create robots, build scenes, run simulations, and debug physics all from your editor.

![Robot Party Demo](https://raw.githubusercontent.com/whats2000/isaacsim-mcp-server/main/media/add_more_robot_into_party.gif)

---

## Highlights

- **39 tools** across 8 categories -- scene, objects, lighting, robots, sensors, materials, assets, simulation
- **107+ robots** auto-discovered from the Isaac Sim asset library (Franka, UR, Unitree, Boston Dynamics, and more)
- **Step-and-observe** debugging -- step the simulation and inspect prim positions, joint states, and physics in one call
- **Hot-reload** -- iterate on Python controllers without restarting Isaac Sim
- **Multi-instance** -- run multiple Isaac Sim sessions side by side on different ports
- Built for **Isaac Sim 5.1.0** with a modular adapter layer for version isolation

---

## Installation

### Option A: pip install (recommended)

```bash
pip install isaacsim-mcp-server
```

This installs the MCP server and the `isaacsim-mcp-server` CLI. You still need the Isaac Sim extension from the repo (see [Launching Isaac Sim](#2-launch-isaac-sim-with-the-extension) below).

### Option B: From source

```bash
git clone https://github.com/whats2000/isaacsim-mcp-server
cd isaacsim-mcp-server
./scripts/setup_python_env.sh
```

### Requirements

| Requirement | Version |
|-------------|---------|
| NVIDIA Isaac Sim | `5.1.0` |
| Python | `3.10+` |
| `uv` | latest (for source install) |

---

## Quick Start

### 1. Set up the environment

If you installed from source:

```bash
./scripts/setup_python_env.sh
```

### 2. Launch Isaac Sim with the extension

```bash
./scripts/run_isaac_sim.sh
```

You should see in the logs:

```
Registered 40 command handlers
Isaac Sim MCP server started on localhost:8766
```

<details>
<summary>Optional: Beaver3D / NVIDIA API keys for 3D generation</summary>

```bash
export BEAVER3D_MODEL="<your beaver3d model name>"
export ARK_API_KEY="<your beaver3d api key>"
export NVIDIA_API_KEY="<your nvidia api key>"
```

</details>

### 3. Connect your IDE

Add the MCP server to your editor. Replace the path with your actual repo location.

<details>
<summary><strong>Claude Code (CLI)</strong></summary>

```bash
claude mcp add isaac-sim /path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh
```

Or edit `~/.claude.json` / `.mcp.json`:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

</details>

<details>
<summary><strong>VS Code</strong></summary>

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "isaac-sim": {
      "command": "/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

</details>

<details>
<summary><strong>Cursor</strong></summary>

Open **Cursor Settings > MCP**, or edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

</details>

<details>
<summary><strong>Claude Desktop</strong></summary>

Edit the config file for your platform:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

</details>

<details>
<summary><strong>Windsurf</strong></summary>

Open **Windsurf Settings > MCP** or edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

</details>

<details>
<summary><strong>JetBrains IDEs</strong></summary>

Go to **Settings > Tools > AI Assistant > MCP Servers** and add the server. See the [JetBrains MCP docs](https://www.jetbrains.com/help/idea/model-context-protocol.html) for details.

</details>

### 4. Start prompting

```text
Check the connection with get_scene_info.
If the scene is empty, create a physics scene.
Add a Franka robot at the origin and a Go1 quadruped at [2, 0, 0].
```

---

## Architecture

```text
MCP Client (IDE)
      |
      v
isaacsim-mcp-server          (PyPI package / CLI)
      |
      v  TCP socket (localhost:8766)
      |
isaac.sim.mcp_extension      (Omniverse extension)
      |
      v
Handlers -> Adapter -> Isaac Sim 5.1.0 APIs
```

---

## Tools

39 tools across 8 categories:

| Category | Count | What you can do |
|----------|------:|-----------------|
| **Scene** | 7 | Inspect scenes, create physics, list/load environments, browse prims |
| **Objects** | 4 | Create, delete, transform, and clone primitives |
| **Lighting** | 2 | Create and tune lights |
| **Robots** | 6 | Spawn 107+ robots, inspect joints, set positions, refresh library |
| **Sensors** | 4 | Create cameras/LiDAR, capture images, get point clouds |
| **Materials** | 2 | Create and apply materials |
| **Assets** | 4 | Import URDF, load/search USD, generate 3D models |
| **Simulation** | 10 | Play/pause/stop/step, execute Python, inspect physics, hot-reload |

<details>
<summary>Full tool list</summary>

**Scene:** `get_scene_info` `create_physics_scene` `clear_scene` `list_prims` `get_prim_info` `list_environments` `load_environment`

**Objects:** `create_object` `delete_object` `transform_object` `clone_object`

**Lighting:** `create_light` `modify_light`

**Robots:** `create_robot` `list_available_robots` `refresh_robot_library` `get_robot_info` `set_joint_positions` `get_joint_positions`

**Sensors:** `create_camera` `capture_image` `create_lidar` `get_lidar_point_cloud`

**Materials:** `create_material` `apply_material`

**Assets:** `import_urdf` `load_usd` `search_usd` `generate_3d`

**Simulation:** `play_simulation` `pause_simulation` `stop_simulation` `step_simulation` `set_physics_params` `execute_script` `get_simulation_state` `get_physics_state` `get_joint_config` `reload_script`

</details>

---

## Example Prompts

**Scene bootstrap**
```text
Check the connection with get_scene_info. If the scene is empty, create a physics scene.
Add stronger lighting and place a camera that looks at the workspace.
```

**Robot layout**
```text
Create three Franka robots in a row at [0,0,0], [2,0,0], and [4,0,0].
Then add a Go1 robot at [1, 3, 0].
```

**Environment loading**
```text
List available environments, choose a warehouse-like one, and load it.
Create a camera and capture an image.
```

**Asset search and 3D generation**
```text
Search for a rusty desk, load the best result near [0, 5, 0], scaled to [2, 2, 2].
```

---

## Advanced Usage

### Multiple Instances

Run multiple Isaac Sim sessions side by side. Each uses a different port (auto-assigned from `8766`).

```bash
# First instance (default port 8766)
claude mcp add isaac-sim /path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh

# Second instance (port 8767)
claude mcp add isaac-sim-2 -e ISAAC_MCP_PORT=8767 -- /path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh
```

<details>
<summary>JSON config for multiple instances</summary>

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    },
    "isaac-sim-2": {
      "command": "/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh",
      "env": { "ISAAC_MCP_PORT": "8767" }
    }
  }
}
```

</details>

### Desktop Launcher (Linux)

Install a dedicated **Isaac Sim MCP** application icon:

```bash
./scripts/install_desktop_entry.sh
```

This creates a launcher that auto-assigns ports, waits for the extension socket, and cleans up on exit.

### Recommended Workflow

1. Start with `get_scene_info` to verify the connection
2. Create a physics scene if the stage is empty
3. Prefer purpose-built tools before `execute_script`
4. Use `list_available_robots` / `list_environments` before loading
5. Use `step_simulation` with `observe_prims` and `observe_joints` for debugging
6. Use `reload_script` to iterate on controllers without restarting

---

## Demo: Franka Pick-and-Place

A ready-to-run demo at `demo/franka_pick_place.py` using RMPflow for motion planning:

```text
1. Create a physics scene, ground plane, and a Franka FR3 robot
2. Add two tables and a small cube on the first table
3. Wire the pick-and-place script into an Action Graph
4. Press Play -- the robot picks the cube and places it on the second table
```

Uses the observability tools: `get_joint_config`, `step_simulation` with `observe_prims`, `get_physics_state`, and `reload_script`.

---

## Development

```bash
# Run the MCP inspector
./.venv/bin/python -m mcp dev ./isaac_mcp/server.py
```

The inspector is available at `http://localhost:5173`.

### Setup Notes

| Script | Purpose | Default |
|--------|---------|---------|
| `setup_python_env.sh` | Create venv and install package | Python 3.10 |
| `run_isaac_sim.sh` | Launch Isaac Sim with extension | `$HOME/isaacsim` |
| `run_mcp_server.sh` | Start the MCP server | Port 8766 |
| `launch_isaac_sim_mcp.sh` | Combined launcher | Auto-assigns port |
| `dev_mcp_server.sh` | Dev server with hot-reload | Port 8766 |

Override defaults:

```bash
PYTHON_SPEC=3.11 ./scripts/setup_python_env.sh
ISAACSIM_ROOT=/opt/isaacsim ./scripts/run_isaac_sim.sh
```

<details>
<summary>Troubleshooting</summary>

If Isaac Sim says `Can't find extension with name: isaac.sim.mcp_extension`:

```bash
# Make sure you're in the repo root
pwd
test -f ./isaac.sim.mcp_extension/config/extension.toml && echo OK
```

Note: `--ext-folder` must point to the **repo root**, not to `isaac.sim.mcp_extension/` directly.

</details>

---

## Contributing

Pull requests are welcome. Improvements to tools, docs, adapters, and tests are all useful.

## License

MIT License. Copyright (c) 2023-2025 omni-mcp, Copyright (c) 2026 whats2000. See [LICENSE](LICENSE).
