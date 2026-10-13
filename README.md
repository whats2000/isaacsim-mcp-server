# Isaac Sim MCP Server

<!-- mcp-name: io.github.whats2000/isaacsim-mcp-server -->

[![PyPI version](https://img.shields.io/pypi/v/isaacsim-mcp-server)](https://pypi.org/project/isaacsim-mcp-server/)
[![Isaac Sim 5.1.0 - 6.0.1](https://img.shields.io/badge/Isaac_Sim-5.1.0_--_6.0.1-76b900)](https://developer.nvidia.com/isaac-sim)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Quality](https://archestra.ai/mcp-catalog/api/badge/quality/whats2000/isaacsim-mcp-server)](https://archestra.ai/mcp-catalog/api/badge/quality/whats2000/isaacsim-mcp-server)
[![isaacsim-mcp-server MCP server](https://glama.ai/mcp/servers/whats2000/isaacsim-mcp-server/badges/score.svg)](https://glama.ai/mcp/servers/whats2000/isaacsim-mcp-server)

> Natural language control for NVIDIA Isaac Sim through the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP).

Connect any MCP-compatible IDE (Cursor, VS Code, Claude Code, Windsurf, Antigravity, JetBrains) to a running Isaac Sim instance and control it with plain-English prompts -- create robots, build scenes, run simulations, and debug physics all from your editor.

![Robot Simulate Demo](https://raw.githubusercontent.com/whats2000/isaacsim-mcp-server/main/media/franka_pick_place.gif)

---

## Highlights

- **42 tools** across 9 categories -- scene, objects, lighting, robots, sensors, materials, assets, simulation, graphs
- **107+ robots** auto-discovered from the Isaac Sim asset library (Franka, UR, Unitree, Boston Dynamics, and more)
- **Step-and-observe** debugging -- step the simulation and inspect prim positions, joint states, and physics in one call
- **Hot-reload** -- iterate on Python controllers without restarting Isaac Sim
- **Multi-instance** -- run multiple Isaac Sim sessions side by side on different ports
- Built for **Isaac Sim 5.1.0 - 6.0.1** (PhysX + Newton) with a modular adapter layer for version isolation

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
| NVIDIA Isaac Sim | `5.1.0` - `6.0.1` (PhysX or Newton) |
| Python | `3.10+` |
| `uv` | latest (for source install) |
| Platform | Linux (Ubuntu 22.04+) or Windows 10/11 |

> [!IMPORTANT]
> **Linux** and **Windows** are supported. On Windows, use the PowerShell
> launcher `scripts/run_isaac_sim.ps1` in place of the `.sh` scripts (see below).
> macOS is not supported because NVIDIA Isaac Sim does not run on macOS.

> [!NOTE]
> We are welcoming contributions to support other Isaac Sim versions. 
> The adapter layer is designed for easy version isolation.

---

## Quick Start

### 1. Set up the environment

If you installed from source:

```bash
./scripts/setup_python_env.sh
```

**On Windows**, `uv sync` creates the virtual environment (`.venv`) and installs
the package plus its dependencies:

```powershell
uv sync
```

### 2. Launch Isaac Sim with the extension

```bash
./scripts/run_isaac_sim.sh
```

You should see in the logs:

```
Registered 42 command handlers
Isaac Sim MCP server started on localhost:8766
```

The script looks for Isaac Sim in `$HOME/isaacsim`; set `ISAACSIM_ROOT` to use a
different install.

**Choosing the physics engine.** Isaac Sim 6.0+ ships PhysX (default) and Newton
backends. Select one with `--newton` / `--physx`, or `ISAACSIM_ENGINE`:

```bash
./scripts/run_isaac_sim.sh                  # PhysX (default)
./scripts/run_isaac_sim.sh --newton         # Newton
ISAACSIM_ENGINE=newton ./scripts/run_isaac_sim.sh
```

The same flags work with `scripts/launch_isaac_sim_mcp.sh`. Everything else on
the command line is forwarded to Kit untouched. The server auto-detects the
active engine, so no MCP-side configuration changes. Newton requires 6.0 or
newer; asking for it on 5.1.0 fails with a clear message.

**On Windows**, use the PowerShell launcher instead. It takes the same engine
selection and forwards extra arguments to Kit:

```powershell
.\scripts\run_isaac_sim.ps1                          # PhysX (default)
.\scripts\run_isaac_sim.ps1 -Engine newton           # Newton
$env:ISAACSIM_ENGINE = 'newton'; .\scripts\run_isaac_sim.ps1
```

The script resolves the install from `-IsaacSimRoot`, then `$env:ISAACSIM_ROOT`,
then a local source build, then `C:\isaacsim`, then `%USERPROFILE%\isaacsim`. It
also creates a writable USD working directory (`.cache\usd`) since Windows has no
`/tmp`.

<details>
<summary>Optional: Beaver3D / NVIDIA API keys for 3D generation</summary>

```bash
export BEAVER3D_MODEL="<your beaver3d model name>"
export ARK_API_KEY="<your beaver3d api key>"
export NVIDIA_API_KEY="<your nvidia api key>"
```

On Windows (PowerShell):

```powershell
$env:BEAVER3D_MODEL = "<your beaver3d model name>"
$env:ARK_API_KEY = "<your beaver3d api key>"
$env:NVIDIA_API_KEY = "<your nvidia api key>"
```

</details>

### 3. Connect your IDE

Add the MCP server to your editor. Replace the path with your actual repo location.
The `command` examples are for **Linux/macOS**; each guide shows the **Windows**
equivalent, which wraps the PowerShell launcher `scripts\run_mcp_server.ps1`.

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

On Windows, wrap the PowerShell launcher:

```bash
claude mcp add isaac-sim -- powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\isaacsim-mcp-server\scripts\run_mcp_server.ps1
```

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "powershell",
      "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\path\\to\\isaacsim-mcp-server\\scripts\\run_mcp_server.ps1"]
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

On Windows, wrap the PowerShell launcher:

```json
{
  "servers": {
    "isaac-sim": {
      "command": "powershell",
      "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\path\\to\\isaacsim-mcp-server\\scripts\\run_mcp_server.ps1"]
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

On Windows, wrap the PowerShell launcher:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "powershell",
      "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\path\\to\\isaacsim-mcp-server\\scripts\\run_mcp_server.ps1"]
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

On Windows, wrap the PowerShell launcher:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "powershell",
      "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\path\\to\\isaacsim-mcp-server\\scripts\\run_mcp_server.ps1"]
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

On Windows, wrap the PowerShell launcher:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "powershell",
      "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\path\\to\\isaacsim-mcp-server\\scripts\\run_mcp_server.ps1"]
    }
  }
}
```

</details>

<details>
<summary><strong>Antigravity</strong></summary>

Open the agent side panel, click **…** > **MCP Servers** > **Manage MCP Servers** >
**View raw config**, or edit `~/.gemini/config/mcp_config.json` (global) or
`.agents/mcp_config.json` (workspace):

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh"
    }
  }
}
```

On Windows, wrap the PowerShell launcher:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "powershell",
      "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\path\\to\\isaacsim-mcp-server\\scripts\\run_mcp_server.ps1"]
    }
  }
}
```

</details>

<details>
<summary><strong>JetBrains IDEs</strong></summary>

Go to **Settings > Tools > AI Assistant > MCP Servers** and add the server, with
the command `/path/to/isaacsim-mcp-server/scripts/run_mcp_server.sh`. See the
[JetBrains MCP docs](https://www.jetbrains.com/help/ai-assistant/configure-an-mcp-server.html) for details.

On Windows, set the command to `powershell` and the arguments to
`-NoProfile -ExecutionPolicy Bypass -File C:\path\to\isaacsim-mcp-server\scripts\run_mcp_server.ps1`.

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
Handlers -> Adapter -> Isaac Sim 5.1 / 6.0 APIs
```

---

## Tools

42 tools across 9 categories:

| Category | Count | What you can do |
|----------|------:|-----------------|
| **Scene** | 7 | Inspect scenes, create physics, list/load environments, browse prims |
| **Objects** | 4 | Create, delete, transform, and clone primitives |
| **Lighting** | 2 | Create and tune lights |
| **Robots** | 6 | Spawn 107+ robots, inspect joints, set positions, refresh library |
| **Sensors** | 4 | Create cameras/LiDAR, capture images, get point clouds |
| **Materials** | 2 | Create and apply materials |
| **Assets** | 4 | Import URDF, load/search USD, generate 3D models |
| **Graphs** | 2 | Build and edit Action Graphs (OnPlaybackTick, ScriptNode, script file attachment) |
| **Simulation** | 11 | Play/pause/stop/step, execute Python, inspect physics, hot-reload |

<details>
<summary>Full tool list</summary>

**Scene:** `get_scene_info` `create_physics_scene` `clear_scene` `list_prims` `get_prim_info` `list_environments` `load_environment`

**Objects:** `create_object` `delete_object` `transform_object` `clone_object`

**Lighting:** `create_light` `modify_light`

**Robots:** `create_robot` `list_available_robots` `refresh_robot_library` `get_robot_info` `set_joint_positions` `get_joint_positions`

**Sensors:** `create_camera` `capture_image` `create_lidar` `get_lidar_point_cloud`

**Materials:** `create_material` `apply_material`

**Assets:** `import_urdf` `load_usd` `search_usd` `generate_3d`

**Graphs:** `create_action_graph` `edit_action_graph`

**Simulation:** `play_simulation` `pause_simulation` `stop_simulation` `step_simulation` `set_physics_params` `get_isaac_logs` `get_simulation_state` `get_physics_state` `get_joint_config` `execute_script` `reload_script`

</details>

---

## Known Limitations

Open defects a normal session can hit. Each is warned about at the
point of use where that is possible; this list is for choosing a runtime before
you start.

| Affects | What happens | Issue |
|---|---|---|
| 6.0 Newton | Joint drives do not converge — a commanded target is overshot and the joint keeps going, and joint limits are not enforced. Scene setup, stepping and inspection are fine; run motion work on PhysX (`isaac-sim.sh`). | [#21](https://github.com/whats2000/isaacsim-mcp-server/issues/21) |
| 6.0 | The first RTX camera created in a session cannot be removed. `create_camera` warns once when it hands you that camera. | [#20](https://github.com/whats2000/isaacsim-mcp-server/issues/20) |
| 5.1 | `get_lidar_point_cloud` fills on roughly a third of reads, so a caller must retry. A lidar created while the timeline is running never fills at all — create it stopped. | [#31](https://github.com/whats2000/isaacsim-mcp-server/issues/31) |
| 5.1 | An RTX lidar prim cannot be deleted; the prim is left behind as a `Camera`. `create_lidar` refuses such a path and names a free one. | [#25](https://github.com/whats2000/isaacsim-mcp-server/issues/25) |

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

### Browser Live View (headless)

On a headless machine (a cloud GPU, a server with no monitor), add `--live-view` to watch the
simulation in a browser while you prompt your IDE:

```bash
./scripts/run_isaac_sim.sh --no-window --live-view
# or: ISAAC_LIVE_VIEW=1 ./scripts/run_isaac_sim.sh --no-window
```

Isaac Sim then serves a page on `http://127.0.0.1:18200/` with the camera feed (MJPEG), the
timeline state, and orbit/tilt/zoom buttons. It renders whether the simulation is playing or
stopped, so scene edits appear as soon as a tool call finishes.

- **Remote access:** it listens on localhost only. From your own computer, tunnel to it with
  `ssh -L 18200:127.0.0.1:18200 user@gpu-host` and open `http://localhost:18200/`, or put it
  behind a reverse proxy that does authentication. The page has no authentication of its own.
- **Port:** set `ISAAC_LIVE_VIEW_PORT` (and `ISAAC_LIVE_VIEW_HOST` to bind elsewhere).
- **Camera:** it renders `/OmniverseKit_Persp`, which survives `clear_scene`. To aim it from a
  prompt, `execute_script` with
  `import builtins; builtins._live_view["look_at"]([2.5, -1.5, 1.4], [0.4, 0.0, 0.4])`.
- **Already running Isaac Sim?** Start it without a restart through `execute_script`:
  `exec(open("/path/to/isaacsim-mcp-server/scripts/live_view.py").read())`.
- **Limits:** watch-only video (not an interactive viewport), about 30–40 fps on an RTX 4090,
  and the flag is Linux-only for now.

### Recommended Workflow

1. Start with `get_scene_info` to verify the connection
2. Create a physics scene if the stage is empty
3. Prefer purpose-built tools before `execute_script`
4. Use `list_available_robots` / `list_environments` before loading
5. Use `create_action_graph` to wire OnPlaybackTick → ScriptNode controllers
6. Use `step_simulation` with `observe_prims` and `observe_joints` for debugging
7. Use `reload_script` to iterate on controllers without restarting

---

## Demo: Franka Pick-and-Place

A ready-to-run demo at `demo/franka_pick_place.py` using RMPflow for motion planning:

```text
Please use the Isaac MCP tool complete this:

Create a physics scene with a ground plane, then spawn a Franka FR3 robot at the origin.

Add two textured tables with a gap along Y. Place a small textured cube with physics enabled on top of the first table.

Use `create_action_graph` to wire `OnPlaybackTick` → `ScriptNode`, and write a pick-and-place controller script using RMPflow for motion planning. Save the script to the `demo/` directory.

Use `get_prim_info` to query actual positions and sizes of the tables and cube before writing the controller — do not hardcode coordinates.

Start the simulation with Play. The robot should pick the cube from table 1 and place it on table 2. Verify the process using `step_simulation` with `observe_prims` on the cube to confirm it reaches table 2.
```

Uses `create_action_graph` with `script_file` for one-step Action Graph + ScriptNode setup, plus the observability tools: `get_joint_config`, `step_simulation` with `observe_prims`, `get_physics_state`, and `edit_action_graph` for script hot-reload.

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
| `run_isaac_sim.sh` | Launch Isaac Sim with extension (Linux) | `$HOME/isaacsim` |
| `run_isaac_sim.ps1` | Launch Isaac Sim with extension (Windows) | `C:\isaacsim` |
| `run_mcp_server.sh` | Start the MCP server (Linux) | Port 8766 |
| `run_mcp_server.ps1` | Start the MCP server (Windows) | Port 8766 |
| `launch_isaac_sim_mcp.sh` | Combined launcher | Auto-assigns port |
| `dev_mcp_server.sh` | Dev server with hot-reload | Port 8766 |

Override defaults:

```bash
PYTHON_SPEC=3.11 ./scripts/setup_python_env.sh
ISAACSIM_ROOT=/opt/isaacsim ./scripts/run_isaac_sim.sh
ISAACSIM_ENGINE=newton ./scripts/run_isaac_sim.sh
ISAAC_LIVE_VIEW=1 ISAAC_LIVE_VIEW_PORT=18300 ./scripts/run_isaac_sim.sh --no-window
```

Engine selection lives in `scripts/lib/isaac_launcher.sh`: each engine maps to
the launcher script Isaac Sim ships for it. Adding an entry to that map is all a
new backend needs — it enables both `ISAACSIM_ENGINE=<name>` and `--<name>` in
every launcher script.

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
