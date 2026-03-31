# Isaac Sim MCP Extension and MCP Server

The MCP Server and its extension leverage the Model Context Protocol (MCP) framework to enable natural language control of NVIDIA Isaac Sim, transforming conversational AI inputs into precise simulation manipulation. This expansion bridges the MCP ecosystem with embodied intelligence applications.

## Features

- Natural language control of Isaac Sim
- Modular tool architecture with 31 specialized tools across 8 categories
- Dynamic robot positioning and movement
- Custom lighting and scene creation
- Advanced robot simulations with obstacle navigation
- Interactive code preview before execution
- Full support for NVIDIA Isaac Sim 5.1.0
- USD asset search and 3D asset generation via Beaver3D

## Requirements

- NVIDIA Isaac Sim 5.1.0 or higher
- Python 3.11+
- Cursor AI editor for MCP integration

## **Mandatory** Pre-requisite

- Install uv/uvx: [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)
- Install mcp[cli] to base env: [uv pip install "mcp[cli]"](https://pypi.org/project/mcp/)

## Installation

```bash
cd ~/Documents
git clone https://github.com/omni-mcp/isaac-sim-mcp
```

### Install and Enable Extension

Isaac Sim extension folder should point to your project folder:
- Extension location: `~/Documents/isaac-sim-mcp` 
- Extension ID: `isaac.sim.mcp_extension`

```bash
# Enable extension in Isaac Simulation
# cd to your Isaac Sim installation directory
# You can change assets root to local with --/persistent/isaac/asset_root/default="<your asset location>"
# By default it is an AWS bucket, e.g. --/persistent/isaac/asset_root/default="/share/Assets/Isaac/5.1"
# Setup API KEY for Beaver3d and NVIDIA
export BEAVER3D_MODEL=<your beaver3d model name>
export ARK_API_KEY=<Your Bearver3D API Key>
export NVIDIA_API_KEY="<your nvidia api key  and apply it from https://ngc.nvidia.com/signout>"

cd ~/isaacsim
./isaac-sim.sh --ext-folder ~/Documents/isaac-sim-mcp/ --enable isaac.sim.mcp_extension 
```

Verify the extension starts successfully. The output should look like:

```
[ext: isaac.sim.mcp_extension-0.3.0] startup
trigger  on_startup for:  isaac.sim.mcp_extension-0.3.0
Server thread startedIsaac Sim MCP server started on localhost:8766
```

The extension should be listening at **localhost:8766** by default.



### Install MCP Server

1. Go to terminal and run, make sure mcp server could start sucessfully at terminal with base venv.
   ```
   uv pip install "mcp[cli]"
   uv run ~/Documents/isaac-sim-mcp/isaac_mcp/server.py
   ```
2. Start Cursor and open the folder `~/Documents/isaac-sim-mcp`
3. Go to Cursor preferences, choose MCP and add a global MCP server:

```json
{
    "mcpServers": {
        "isaac-sim": {
            "command": "uv run ~/Documents/isaac-sim-mcp/isaac_mcp/server.py"
        }
    }
}
```

### Development Mode

To develop the MCP Server, start the MCP inspector:

```bash
uv run mcp dev ~/Documents/isaac-sim-mcp/isaac_mcp/server.py
```

You can visit the debug page through http://localhost:5173

## Example Prompts for Simulation
Notice: Switch to Agent mode in top left of Chat dialog before you type prompt and choose sonnet 3.7 for better coding.

### Robot Party
```
# Create robots and improve lighting
create  3x3 frankas robots in these current stage across location [3, 0, 0] and [6, 3, 0]
always check connection with get_scene_info before execute code.
add more light in the stage


# Add specific robots at positions
create a g1 robot at [3, 9, 0]
add Go1 robot at location [2, 1, 0]
move go1 robot to [1, 1, 0]
```

### Factory Setup
```
# Create multiple robots in a row
acreate  3x3 frankas robots in these current stage across location [3, 0, 0] and [6, 3, 0]
always check connection with get_scene_info before execute code.
add more light in the stage


```
### Vibe Coding from scratch
```
reference to g1.py to create an new g1 robot simulation and allow robot g1 walk straight  from [0, 0, 0] to [3, 0, 0] and [3, 3, 0]
create more obstacles in the stage

```
### Gen3D with beaver3d model support

```
Use following images to generate beaver 3d objects and place them into a grid area across [0, 0, 0] to [40, 40, 0] with scale [3, 3, 3]

<your image url here, could be multiple images urls>
```

### USD search
```
search a rusty desk and place it at [0, 5, 0] with scale [3, 3, 3]
```

## MCP Tools

The Isaac Sim MCP Extension exposes 31 specialized tools organized into 8 categories. All tools are accessible through natural language in Cursor AI and communicate with the Isaac Sim extension running on `localhost:8766`.

### Scene Management (5 tools)

- **get_scene_info** - Pings the Isaac Sim Extension Server to verify connection status and retrieve basic scene information. Always use this first to confirm the connection is active.

- **create_physics_scene** - Creates a physics scene with configurable parameters:
  - `objects`: List of objects to create (each with type and position)
  - `floor`: Whether to create a ground plane (default: `true`)
  - `gravity`: Vector defining gravity direction and magnitude (default: `[0, -9.81, 0]`)
  - `scene_name`: Name for the scene (default: `"physics_scene"`)

- **clear_scene** - Removes all user-created prims from the current stage, leaving the default lighting and camera intact.

- **list_prims** - Returns a list of all prims (objects) currently present in the stage, including their paths and types.

- **get_prim_info** - Retrieves detailed information about a specific prim:
  - `prim_path`: USD path of the prim to inspect (e.g., `"/World/Franka"`)

### Object Creation (4 tools)

- **create_object** - Creates a geometric primitive or mesh in the scene:
  - `prim_type`: Shape type (e.g., `"Sphere"`, `"Cube"`, `"Cylinder"`, `"Cone"`, `"Plane"`)
  - `prim_path`: USD path for the new object (e.g., `"/World/MySphere"`)
  - `position`: `[x, y, z]` position coordinates
  - `scale`: `[x, y, z]` scale factors (optional)
  - `color`: `[r, g, b]` color values in 0–1 range (optional)

- **delete_object** - Deletes a prim from the stage:
  - `prim_path`: USD path of the prim to delete

- **transform_object** - Moves, rotates, or scales an existing prim:
  - `prim_path`: USD path of the target prim
  - `position`: `[x, y, z]` new position (optional)
  - `rotation`: `[x, y, z]` Euler angles in degrees (optional)
  - `scale`: `[x, y, z]` new scale factors (optional)

- **clone_object** - Duplicates an existing prim to a new path:
  - `source_path`: USD path of the prim to clone
  - `target_path`: USD path for the cloned copy
  - `position`: `[x, y, z]` position for the clone (optional)

### Lighting (2 tools)

- **create_light** - Adds a light to the scene:
  - `light_type`: Type of light (`"DistantLight"`, `"SphereLight"`, `"DiskLight"`, `"RectLight"`)
  - `prim_path`: USD path for the new light
  - `intensity`: Light intensity value
  - `color`: `[r, g, b]` light color in 0–1 range (optional)
  - `position`: `[x, y, z]` position coordinates (optional)

- **modify_light** - Updates properties of an existing light:
  - `prim_path`: USD path of the light to modify
  - `intensity`: New intensity value (optional)
  - `color`: New `[r, g, b]` color (optional)

### Robot Control (5 tools)

- **create_robot** - Creates a robot in the scene at a specified position:
  - `robot_type`: Robot type (`"franka"`, `"jetbot"`, `"carter"`, `"g1"`, `"go1"`)
  - `position`: `[x, y, z]` position coordinates
  - `robot_name`: Optional custom name for the robot prim

- **list_available_robots** - Returns a list of all robot types supported by the extension, along with their USD asset paths.

- **get_robot_info** - Retrieves joint names, DOF counts, and current state of a robot:
  - `robot_path`: USD path of the robot prim

- **set_joint_positions** - Commands a robot's joints to target angles:
  - `robot_path`: USD path of the robot
  - `joint_positions`: List of joint angle values (radians)
  - `joint_names`: List of joint names corresponding to the positions (optional)

- **get_joint_positions** - Reads the current joint positions of a robot:
  - `robot_path`: USD path of the robot

### Sensors (4 tools)

- **create_camera** - Adds a camera sensor to the scene:
  - `prim_path`: USD path for the new camera
  - `position`: `[x, y, z]` position coordinates
  - `rotation`: `[x, y, z]` Euler angles in degrees (optional)
  - `focal_length`: Camera focal length in mm (optional)

- **capture_image** - Captures a rendered image from the specified camera:
  - `camera_path`: USD path of the camera
  - `output_path`: File path where the image will be saved (PNG)
  - `resolution`: `[width, height]` in pixels (optional)

- **create_lidar** - Attaches a LiDAR sensor to the scene or to a prim:
  - `prim_path`: USD path for the LiDAR prim
  - `parent_path`: USD path of the parent prim to attach the sensor to (optional)
  - `position`: `[x, y, z]` position coordinates (optional)

- **get_lidar_point_cloud** - Retrieves the latest point cloud data from a LiDAR sensor:
  - `lidar_path`: USD path of the LiDAR prim

### Materials (2 tools)

- **create_material** - Creates an OmniPBR material and optionally writes it to a USD layer:
  - `material_path`: USD path for the new material
  - `color`: `[r, g, b]` base color in 0–1 range (optional)
  - `metallic`: Metallic factor 0–1 (optional)
  - `roughness`: Roughness factor 0–1 (optional)

- **apply_material** - Binds an existing material to a prim:
  - `prim_path`: USD path of the target prim
  - `material_path`: USD path of the material to apply

### Asset Management (4 tools)

- **import_urdf** - Imports a URDF robot description file into the current stage:
  - `urdf_path`: Absolute file path to the `.urdf` file
  - `prim_path`: Destination USD path in the stage (optional)
  - `position`: `[x, y, z]` placement position (optional)

- **load_usd** - Loads a USD or USDA file as a reference into the stage:
  - `usd_path`: Absolute file path or `omniverse://` URL of the USD asset
  - `prim_path`: Destination USD path in the stage (optional)
  - `position`: `[x, y, z]` placement position (optional)

- **search_usd** - Searches the NVIDIA Omniverse asset library for USD assets matching a query:
  - `query`: Natural language search term (e.g., `"rusty desk"`, `"warehouse shelf"`)
  - `max_results`: Maximum number of results to return (default: `5`)

- **generate_3d** - Generates a 3D asset from an image URL using the Beaver3D model and places it in the scene:
  - `image_url`: Publicly accessible URL of the source image
  - `prim_path`: Destination USD path in the stage
  - `position`: `[x, y, z]` placement position (optional)
  - `scale`: `[x, y, z]` scale factors (optional)

### Simulation Control (6 tools)

- **play_simulation** - Starts the physics simulation timeline.

- **pause_simulation** - Pauses the running simulation while preserving the current state.

- **stop_simulation** - Stops and resets the simulation timeline to the beginning.

- **step_simulation** - Advances the simulation by a specified number of physics steps:
  - `num_steps`: Number of steps to advance (default: `1`)

- **set_physics_params** - Adjusts global physics parameters at runtime:
  - `gravity`: `[x, y, z]` gravity vector (optional)
  - `dt`: Physics timestep in seconds (optional)

- **execute_script** - Executes arbitrary Python code inside Isaac Sim, giving full access to the Omniverse Kit API:
  - `code`: Python code string to execute

### Usage Best Practices

1. Always verify the connection with `get_scene_info` before sending any commands.
2. Call `create_physics_scene` to establish a physics environment before adding robots or dynamic objects.
3. Use category-specific tools (e.g., `create_robot`, `create_light`) before falling back to `execute_script` for complex logic.
4. Search for assets with `search_usd` and load them with `load_usd` to populate scenes from the Omniverse asset library.
5. Use `set_joint_positions` and `get_joint_positions` for articulation control; use `execute_script` for multi-step trajectory execution.
6. Call `capture_image` after `play_simulation` or `step_simulation` when sensor data is needed at a specific simulation time.
7. Preview generated code in chat before execution to verify intent and avoid unintended scene modifications.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Video Demonstrations

Below are demonstrations of the Isaac Sim MCP Extension in action:

### Robot Party Demo

![Robot Party Demo](media/add_more_robot_into_party.gif)

*GIF: Adding more robots to the simulation using natural language commands*


### Video Format (MP4)

For higher quality video, you can access the MP4 version directly:

- [Robot Party Demo (MP4)](media/add_more_robot_into_party.mp4)

When viewing on GitHub, you can click the link above to view or download the MP4 file.
