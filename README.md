# Isaac Sim MCP

Natural language control for NVIDIA Isaac Sim through the Model Context Protocol (MCP).

This project connects an MCP server to an Isaac Sim extension so tools like Cursor can inspect scenes, create robots and assets, control simulation, and execute targeted Python inside Isaac Sim from plain-English prompts.

![Robot Party Demo](media/add_more_robot_into_party.gif)

## Why This Project

- Built for NVIDIA Isaac Sim `5.1.0`
- Clean split between MCP server tools and in-sim extension handlers
- `35` tools across `8` categories for scene, robot, sensor, asset, and simulation workflows
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
Cursor / MCP Client
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
- Python `3.11+`
- `uv` / `uvx`
- `mcp[cli]`
- An MCP-compatible client such as Cursor

## Quick Start

### 1. Clone the repo

```bash
cd ~/Documents
git clone https://github.com/omni-mcp/isaac-sim-mcp
cd isaac-sim-mcp
```

### 2. Install MCP prerequisites

```bash
uv pip install "mcp[cli]"
```

### 3. Launch Isaac Sim with the extension enabled

Isaac Sim should load this repository as an extension folder.

- Extension folder: `~/Documents/isaac-sim-mcp`
- Extension id: `isaac.sim.mcp_extension`
- Default socket endpoint: `localhost:8766`

Optional environment variables for Beaver3D and NVIDIA-backed asset workflows:

```bash
export BEAVER3D_MODEL="<your beaver3d model name>"
export ARK_API_KEY="<your beaver3d api key>"
export NVIDIA_API_KEY="<your nvidia api key>"
```

Start Isaac Sim:

```bash
cd ~/isaacsim
./isaac-sim.sh \
  --ext-folder ~/Documents/isaac-sim-mcp \
  --enable isaac.sim.mcp_extension
```

If you use a local Isaac asset root, you can also pass:

```bash
--/persistent/isaac/asset_root/default="<your asset root>"
```

Expected startup logs should include lines similar to:

```text
[ext: isaac.sim.mcp_extension-0.3.0] startup
trigger  on_startup for:  isaac.sim.mcp_extension-0.3.0
Registered 35 command handlers
Isaac Sim MCP server started on localhost:8766
```

### 4. Run the MCP server

```bash
uv run isaac_mcp/server.py
```

### 5. Add the MCP server to Cursor

Open Cursor settings and add:

```json
{
  "mcpServers": {
    "isaac-sim": {
      "command": "uv run ~/Documents/isaac-sim-mcp/isaac_mcp/server.py"
    }
  }
}
```

## Recommended Workflow

When prompting your MCP client:

1. Start with `get_scene_info`
2. Create a physics scene if the stage is empty
3. Prefer purpose-built tools before using `execute_script`
4. Use `list_available_robots` or `list_environments` before fuzzy-matched loading
5. Use `play_simulation`, `pause_simulation`, `stop_simulation`, and `step_simulation` explicitly when timing matters

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

The MCP server currently exposes `35` tools across `8` categories.

| Category | Tools | Highlights |
| --- | ---: | --- |
| Scene | 7 | scene info, physics scene creation, prim inspection, environment discovery/loading |
| Objects | 4 | create, delete, transform, clone primitives |
| Lighting | 2 | create and tune lights |
| Robots | 6 | create robots, inspect joints, refresh library, command articulations |
| Sensors | 4 | camera and lidar creation plus capture / point cloud access |
| Materials | 2 | create and apply materials |
| Assets | 4 | URDF import, USD load/search, Beaver3D generation |
| Simulation | 6 | play, pause, stop, step, set physics, execute Python |

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
- `step_simulation`
- `set_physics_params`
- `execute_script`

## Development

Run the MCP inspector during development:

```bash
uv run mcp dev ~/Documents/isaac-sim-mcp/isaac_mcp/server.py
```

The inspector is typically available at `http://localhost:5173`.

## Demo Media

- [Robot Party Demo (MP4)](media/add_more_robot_into_party.mp4)

## Contributing

Pull requests are welcome. Small improvements to tools, docs, adapters, and tests are all useful.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
