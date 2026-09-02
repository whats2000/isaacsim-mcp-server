# Changelog

All notable changes to the isaacsim-mcp-server project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **`get_prim_info`'s `transform.position` is replaced by `position_local` and `position_world`** ([#39](https://github.com/whats2000/isaacsim-mcp-server/issues/39)). It held the *parent-relative* pose with nothing saying so, while `actual_size` in the same response was world-space. Robot links are where it bit — `/World/Franka/fr3_hand_tcp` — because Isaac's FR3 is a flat hierarchy rooted at the articulation, so a robot at the default origin makes the two frames coincide and the tool look correct; put the robot anywhere else and the same call silently returned base-relative coordinates. Naming one field `position` and the other `position_world` would have kept the trap, so there is no bare `position`: callers must choose a frame. `position_world_source` is `"usd"` or `"physics"`. On Newton the Fabric pose now fills `position_world` instead of overwriting `position` — that overwrite meant one field carried a world value on Newton and a local one everywhere else. `rotation` and `scale` remain local, matching what `transform_object` writes.

### Fixed
- **`step_simulation(observe_prims=...)` reported positions in different frames depending on whether the physics read succeeded.** Its PhysX/tensor branch returns world positions; the USD fallback beneath it returned parent-relative ones, silently, in the field most used to measure motion. Both are world now. Found while fixing #39.
- **`create_camera(target=...)` aimed from the wrong frame.** With no explicit position it read the camera's own pose as the eye point and passed it to a look-at against a **world** target, so a camera nested under a transformed parent was aimed from a parent-relative point — and still produced a rotation, so it failed silently. Found while fixing #39.
- **`load_environment`'s `bounds.floor_height` was the environment's bounding-box minimum, not its floor** ([#38](https://github.com/whats2000/isaacsim-mcp-server/issues/38)). It was documented as the value that lets a caller place objects on the ground, but any geometry dipping below the floor — trim, a recessed drain, a sunk prop — dragged it down: `simple_warehouse` reported `-0.009` against a collision floor at `0.0`, so placing on it embedded the object 9 mm and resolved as a settle or jitter rather than an error. `floor_height` is now derived from the environment's own collision floor, and the bbox minimum is reported separately as `bounds_min_z`. `floor_height_source` says which was used; when no collision floor can be measured it falls back to the bbox minimum, labelled and with a `floor_height_warning`.
- **`load_environment` followed by `create_physics_scene` left two collision floors on the stage** ([#37](https://github.com/whats2000/isaacsim-mcp-server/issues/37)). The ground-plane guard only asked whether `/World/groundPlane` existed, never whether the stage already had a floor, so the documented setup order always stacked a second one. In `simple_warehouse` both sit at z=0 and nothing looks wrong; on an environment whose floor is elsewhere, objects rest at a height nothing explains and which plane wins is PhysX's decision. `create_physics_scene` now skips its plane when a collision-enabled `Plane` is already present, and reports `ground_plane` (the floor objects will land on) and `ground_plane_created`.

## [0.6.1] - 2026-09-01

### Added
- **Releases publish to the MCP Registry** — a tagged release now stamps the tag version into `server.json` and runs `mcp-publisher` (GitHub Actions OIDC, no stored secret) after the PyPI upload. The listing had been hand-published and sat at 0.4.1 while 0.5.0 through 0.6.0 shipped to PyPI.
- **Windows support** — `scripts/run_isaac_sim.ps1` launches Isaac Sim with the extension on Windows 10/11, with the same PhysX/Newton engine selection as the Linux launcher (`-Engine`, `$env:ISAACSIM_ENGINE`, `--physx`/`--newton`). Resolves the install from `-IsaacSimRoot`, `ISAACSIM_ROOT`, a local source build, `C:\isaacsim`, or `%USERPROFILE%\isaacsim`.
- **Antigravity IDE guide** — the README's *Connect your IDE* section now covers Google's Antigravity IDE, with both the global (`~/.gemini/config/mcp_config.json`) and workspace (`.agents/mcp_config.json`) config locations and a Windows PowerShell-launcher variant.

### Fixed
- **Manifest server host/port were read from a settings path Kit never populates.** Kit derives the setting prefix from the extension folder name (`/exts/isaac.sim.mcp_extension/`), but `on_startup` read `/exts/isaac.sim.mcp/` with the wrong key (`server.port` vs `server.socket`), so host and port always fell through to the hardcoded defaults. Now reads the manifest path and falls back to `ISAAC_MCP_PORT` / `ISAAC_MCP_HOST`.
- **USD working directory defaulted to the POSIX-only `/tmp/usd`**, which resolves to a non-writable `C:\tmp\usd` on Windows and broke `search_usd`, `load_usd`, and `generate_3d` before any network call. Now uses the platform temp directory, and an explicitly empty `USD_WORKING_DIR` no longer points the loader at the process working directory.

## [0.6.0] - 2026-08-31

### Added
- **Isaac Sim 6.0.0 support** — new `IsaacAdapterV6` built on `isaacsim.core.experimental.*` + `SimulationManager` + `isaacsim.sensors.experimental.rtx` + `isaacsim.asset.importer.urdf.URDFImporter`. Works under both the PhysX launcher (`isaac-sim.sh`) and the Newton launcher (`isaac-sim.newton.sh`).
- **Newton engine parity** — stepping is engine-aware and frame-exact (`NewtonStage.step_sim`, reported as `stepping: "exact"`); positions come from Fabric, where Newton keeps its simulated transforms; the model is rebuilt when it diverges from the stage; and physics initialisation is refused on geometry the MuJoCo solver cannot build (cones, zero-sized shapes) rather than latching physics dead until Kit restarts.
- **Engine auto-detection** — `adapters/__init__.py:get_adapter()` reads `isaacsim.core.version.get_version()` and selects V5 or V6 by major version. V6 reads `SimulationManager.get_active_physics_engine()` live, never cached.
- **`engine` and `isaacsim_version` fields on `get_simulation_state`** — MCP clients can see the active backend without poking at the runtime.
- **`position_source` on every joint read** — `get_joint_positions`, `step_simulation(observe_joints=...)` and `get_joint_config` all report whether a read measured physics or echoed the last command, and warn when it is an echo. `get_joint_config` drops `position_error` from an echoed read rather than reporting the 0.0 it derives from comparing a target with itself.
- **`create_camera(target=...)`** — aim a camera at a point instead of by euler angles; the response echoes `aimed_at` and the `rotation` applied.
- **`create_action_graph(inline_script=...)`** — one-step OnPlaybackTick → ScriptNode wiring.
- **`get_lidar_point_cloud` returns the cloud** — summary by default, `max_points` for a strided sample, `output_path` to write the sweep as `.npy`.
- **`clear_scene(keep_environment=...)`**; `load_environment` returns the `corrections` USD applied plus `bounds`.
- **`list_prims(recursive=...)`** walks the whole subtree instead of one level, and the response echoes which listing it gave.
- **`create_camera` warns on a 6.0 session's first RTX camera**, which cannot be removed for the life of the process.

### Changed
- V6 URDF import uses `URDFImporter(URDFImporterConfig(...))` instead of the deprecated `URDFCreateImportConfig`/`URDFParseFile`/`URDFImportRobot` kit commands.
- V6 physics state reads route through `SimulationManager.get_physics_simulation_view()` (the `omni.physics.tensors` view), replacing the V5 direct call to `omni.physx.get_physx_interface().get_rigidbody_transformation()` (which is unavailable under the Newton kit).
- V6 sensor methods use `isaacsim.sensors.experimental.rtx.{RtxCamera,CameraSensor,Lidar,LidarSensor}` instead of the deprecated `isaacsim.sensors.camera.Camera` / `isaacsim.sensors.rtx.LidarRtx`.
- **The debug loop is step-only** — `step_simulation` refuses a running timeline; `play_simulation` is for the final continuous run. `stop_simulation` resets to spawn state.
- **Joint limits arrive in the same units as positions**, with `limit_units` per joint; `get_prim_info` reports rotation and scale, not position alone.
- `load_environment` references onto `/Environment/<name>` — read `prim_path` from the response.
- `create_material` accepts `material_path`, `reload_script` accepts `script_file` — FastMCP silently drops unknown keyword arguments.
- `get_isaac_logs` is run-scoped, non-destructive, and captures `print()` as `[PRINT]`.
- `scripts/smoke_test_v6.py` is now `scripts/smoke_test.py` and runs against either runtime.
- Hot-reload (`scripts/dev_mcp_server.sh`) reloads `adapters.units` and `adapters.transforms` as well as `base`/`v5`/`v6`. `v5` and `v6` bind those names at module scope, so edits to the unit conversion or the `look_at` maths were invisible to a reload and a live measurement ran against stale code.
- Live tests require `ISAAC_MCP_LIVE_TESTS=1`. They were armed by a socket probe at import, so `uv run pytest` mutated whatever Isaac Sim happened to be running.

### Fixed
- **Two robots corrupted PhysX's GPU pipeline** — CUDA error 700, garbage joint values, and dead physics still reported as success. Physics is now initialised before any articulation exists.
- **The physics view went stale and nothing rebuilt it** — 0 DOF from the second robot of a session onward, joint commands evaporated, and reads echoed the caller's own command back as a measurement.
- **`import_urdf` reported success while importing nothing.**
- **Eight tools reported success for input that did nothing** — a typo'd prim path, a wrong-length array or an unknown `object_type` read as a completed operation. `create_object` also rejects `size <= 0`, which authored a prim scaled to nothing.
- **`capture_image` on a path with no camera created one**, plus a render product and an SDG graph, then reported "no frame available yet".
- **`step_simulation` accepted a negative frame count** and answered "Stepped -5 frames" without advancing physics.
- **Joint limits were reported in degrees while positions were radians** — clamping to them commanded 25 revolutions.
- **A requested rotation compounded with the prim's existing orientation**, so cameras could not be aimed at all.
- **Environments lost their axis and unit conversion** — a ground standing on edge, 10 km across; 6 of 25 shipped environments on 5.1.
- **`clear_scene` did not clear a loaded environment**, so the next `create_physics_scene` stacked a second ground.
- **Both lidar tools were dead on 5.1**, and the empty-read message gave the wrong advice two times out of three. Reviving them surfaced a second trap that is now refused up front: a lidar re-created on a path that previously held one binds to the `Camera` prim the old sensor left behind and never returns a point.
- **Cameras could not be deleted** — the sensor wrapper re-created the prim a tick later.
- **Commands sent during startup failed with a raw `AttributeError`** — the socket opens seconds before Kit has a stage.
- **`apply_material` leaked a raw USD C++ error** naming NVIDIA's build tree.
- **`pip install isaacsim-mcp-server` produced a package that could not start** — the `mcp` dependency was unbounded, so a fresh install resolved mcp 2.x, where `FastMCP` was renamed and `mcp.server.fastmcp` no longer exists. This affects 0.5.2 on PyPI today, not only this release.
- **`create_object(color=...)` was accepted and discarded** — the parameter was documented and sent, no prim was ever coloured, and the call reported success.
- **`search_usd` dropped `position` and `scale`** — the asset landed at the origin at native scale, reported as success.
- **`set_joint_positions` reported the same success whether or not the robot took the command** — when the articulation refuses it, the values are written to USD drive targets, which move nothing until physics initialises again. The response now carries `command_source` and warns on the fallback.
- **Every validation error was reported as a connection failure** — a typo'd prim path or a bad size came back as "Communication error with Isaac", which reads as a transport fault, and the healthy socket was thrown away and redialled on the next call.
- **`reload_script(module_name=...)` re-ran stale bytecode** — editing a controller and reloading it reported success while the previous version kept running, whenever the edit left the file the same length.
- **`list_prims` returned only immediate children** while documenting "all prims in the scene", so a camera parented under a robot was invisible to a listing that reported success.
- **`edit_action_graph` rejected the relative attribute paths its own docstring documents** — every attribute except `usePath`/`scriptPath` failed with `node=None, graph=None`.

### Notes
- Verified on device on Isaac Sim 5.1.0, 6.0.1 PhysX and 6.0.1 Newton, cold-booted one instance at a time with the GUI.
- Only one Isaac Sim instance can run at a time on a single GPU; a second concurrent instance caused device-lost crashes during testing.

## [0.5.2] - 2026-04-07

### Fixed
- Code style: apply ruff formatting to v5 adapter, graphs handler, and scene handler

## [0.5.1] - 2026-04-06

### Added
- **`edit_action_graph` tool**: Modify attribute values and add connections on existing Action Graphs. Uses `og.Controller.set()` for ScriptNode `usePath`/`scriptPath` attributes (matching the pattern from `omni.graph.scriptnode` official tests). Auto-resets `state:omni_initialized` when script content or path changes to force ScriptNode reload
- **`script_file` parameter on `create_action_graph`**: One-step convenience for the common OnPlaybackTick → ScriptNode workflow. Automatically creates nodes, wires connections, and attaches the script file — replaces the previous two-step create + edit pattern
- **`prim_path` parameter on `create_robot`**: Explicit USD prim path control (e.g. `/World/Franka`) instead of name-based path derivation. Solves the common issue where robots are created at `/{Name}` but scripts expect `/World/{Name}`
- ScriptNode workflow documentation in MCP server instructions covering one-step (`script_file`) and two-step (`create` + `edit`) patterns, script reload via `edit_action_graph`, and `setup(db)`/`compute(db)` function requirements

### Changed
- `create_action_graph` docstring updated with `script_file` example and inline/file-based usage patterns
- `create_robot` docstring updated with `prim_path` parameter documentation
- Tool count updated to 42 across 9 categories

## [0.5.0] - 2026-04-06

### Added
- **`create_action_graph` tool**: Build OmniGraph Action Graphs programmatically (nodes, connections, attribute values) via `og.Controller.edit()` — no more raw `execute_script` calls for OnPlaybackTick → ScriptNode wiring
- **Drive config warnings**: `get_joint_config` and `create_robot` now return a `warnings` array when any joint has `stiffness=0` and `damping=0` (e.g. FR3 `finger_joint2` broken drive)
- **Dimensional data in responses**: `create_object` now returns `actual_size` [x, y, z] in meters and `bounding_box` (min/max world-space corners)
- **Prim size inspection**: `get_prim_info` returns `actual_size` for geometric prims (Cube, Sphere, Cylinder, Cone, Capsule)
- **Inline joint info**: `create_robot` now returns `joint_names` and `num_dof` in the response, eliminating the need for a follow-up `get_robot_info` call
- **Joint limits**: `get_robot_info` now returns `joint_limits` with type (revolute/prismatic), lower/upper limits, and units per joint
- **Comprehensive server instructions**: MCP `instructions` field now includes workflow guidance for scene setup, debug loop (step-and-observe), controller development, and tool priority
- `get_prim_actual_size` adapter method for computing prim dimensions from USD geometry attributes and scale

### Changed
- **Tool docstrings rewritten** with workflow guidance:
  - `step_simulation` promoted as the primary debug tool with typical debug loop example
  - `execute_script` reframed as escape hatch with explicit list of preferred alternatives
  - `reload_script` positioned as the controller loading workflow
  - `get_joint_config`, `get_physics_state`, `get_isaac_logs` marked as diagnostic tools with when-to-call guidance
  - `set_joint_positions`, `get_joint_positions` now document units (radians/meters)
  - `create_object` documents default primitive sizes and scale behavior
- Replaced `asset_creation_strategy` prompt with inline `instructions` covering MCP vs Script/Action Graph scope
- Updated package name and version in extension.toml
- Added new application icon and social badge image

### Fixed
- **Ground plane collision**: `create_physics_scene` now applies `UsdPhysics.CollisionAPI` to the ground plane — objects no longer fall through the floor
- **Stale `.pyc` in `reload_script`**: Dev script now clears bytecode cache before `importlib.reload()` for both extension and user modules, preventing stale code from loading
- **Orphaned subscriptions**: `reload_script` exec() mode now cleans up subscriptions from previous runs before re-executing
- Dev hot-reload script: bypass pybind11 `__setattr__` on `omni.ext.IExt` subclasses using `__dict__` assignment
- Dev hot-reload script: use `isinstance(obj, MCPExtension)` instead of fragile `hasattr` checks that matched wrong objects
- Dev hot-reload script: clear stale `.pyc` files before `importlib.reload()` to ensure fresh source is loaded
- Use `Usd.TimeCode.Default()` instead of non-existent `Gf.TimeCode(0)` in `get_prim_actual_size`
- World-space (not local-space) transform for bounding box computation
- Cylinder/Cone axis attribute respected when computing dimensions

## [0.4.1] - 2026-04-02

### Changed
- Added MCP registry metadata (`server.json`) for marketplace listing
- Fixed demo GIF URL in README to use absolute GitHub raw URL

## [0.4.0] - 2026-04-02

### Added
- **Observability tools**: `get_simulation_state`, `get_physics_state`, `get_joint_config`, `get_isaac_logs`, `reload_script`
- **Step-and-observe**: `observe` parameters on `step_simulation` for combined stepping and inspection (issue #8)
- `cwd` parameter and stdout/stderr capture for `execute_script`
- Franka pick-and-place demo scene and USD file
- Development wrapper for MCP server with hot-reloading support
- Environment discovery and loading tools
- Dynamic robot discovery from Isaac Sim asset server
- PyPI packaging via `pyproject.toml` — installable with `pip install isaacsim-mcp-server`
- Tag-triggered PyPI publish and GitHub Release CD pipeline
- Smithery registry manifest
- CI lint and format checks on PRs (ruff)
- Desktop launcher instructions and scripts
- Documentation for running multiple Isaac Sim instances with MCP

### Changed
- **Renamed package** from `isaac-sim-mcp` to `isaacsim-mcp-server` across all references
- Complete modular architecture rewrite:
  - Extracted `IsaacConnection` into dedicated connection module
  - Added adapter layer with base ABC and v5 implementation
  - Split into 8 handler modules with 31+ command handlers
  - Split into 8 MCP tool modules with 31+ tools
  - Rewrote `server.py` as slim entry point using modular tools
  - Rewrote `extension.py` as slim registry-based command router
  - Extracted socket server from `extension.py`
- Added type hints across all handler, adapter, and connection modules
- Migrated all imports from `omni.isaac.*` to `isaacsim.*` for Isaac Sim 5.1.0 compatibility
- Refreshed project documentation to reflect the current Isaac Sim `5.1.0`-focused architecture
- Reworked the README with a clearer quickstart, architecture overview, and example prompting workflow
- Updated build scripts to use installed `isaacsim-mcp-server` CLI
- Added MIT License to all source files; updated copyright headers for fork continuation
- Now documents `39` MCP tools across `8` categories

### Fixed
- Correct argument order in `set_channel_enabled` (issue #2 bug 1)
- Use PhysX velocity API for accurate runtime readings (issue #2 bug 2)
- Read runtime joint targets from articulation controller (issue #2 bug 3)
- Flatten `execute_script` and `reload_script` response structure (issue #2 bug 4)
- Use `add_message_consumer` API for Isaac Sim 5.1 log listener
- Compare log level enum by value for Isaac Sim 5.1 compatibility
- Use USD `RigidBodyAPI` velocity attrs instead of missing PhysX methods
- Initialize `SingleArticulation` before accessing controller APIs
- `scene.clear` now removes all user prims including root-level ones
- Fix transform precision conflict and URDF file validation
- Remove dead code and fix adapter bypass in handlers

### Tests
- Added 43 integration tests for all tool categories
- Updated structural tests for new observability methods

## [0.3.0] - 2025-04-22

### Added
- USD asset search integration with `search_3d_usd_by_text` tool
- Ability to search and load pre-existing 3D models from USD libraries
- Support for custom positioning and scaling of USD models
- Direct model transformation capabilities with the improved `transform` tool
- Enhanced scene management with multi-object placement

### Improved
- Scene object manipulation with precise positioning controls
- Asset loading performance and reliability
- Error handling for model search and placement
- Integration with existing physics scene management

### Technical Details
- Advanced USD model retrieval system
- Optimized asset loading pipeline
- Position and scale customization for USD models
- Better compatibility with Isaac Sim's native USD handling

## [0.2.1] - 2025-04-15

### Added
- Beaver3D integration for 3D model generation from text prompts and images
- Asynchronous model loading with asyncio support
- Task caching system to prevent duplicate model generation
- New MCP tools:
  - `generate_3d_from_text_or_image` for AI-powered 3D asset creation
  - `transform` for manipulating generated 3D models in the scene
- Texture and material binding for generated 3D models

### Improved
- Asynchronous command execution with `run_coroutine`
- Error handling and reporting for 3D generation tasks
- Performance optimizations for model loading

### Technical Details
- Integration with Beaver3D API for 3D generation
- Task monitoring with callback support
- Position and scale customization for generated models

## [0.1.0] - 2025-04-02

### Added
- Initial implementation of Isaac Sim MCP Extension
- Natural language control interface for Isaac Sim through MCP framework
- Core robot manipulation capabilities:
  - Dynamic placement and positioning of robots (Franka, G1, Go1, Jetbot)
  - Robot movement controls with position updates
  - Multi-robot grid creation (3x3 arrangement support)
- Advanced simulation features:
  - Quadruped robot walking simulation with waypoint navigation
  - Physics-based interactions between robots and environment
  - Custom lighting controls for better scene visualization
- Environment enrichment:
  - Various obstacle types: boxes, spheres, cylinders, cones
  - Wall creation for maze-like environments
  - Dynamic obstacle placement with customizable properties
- Development tools:
  - MCP server integration with Cursor AI
  - Debug interface accessible via local web server
  - Connection status verification with `get_scene_info`
- Documentation:
  - Installation instructions
  - Example prompts for common simulation scenarios
  - Configuration guidelines

### Technical Details
- Extension server running on localhost:8766
- Compatible with NVIDIA Isaac Sim 4.2.0
- Support for Python 3.9+
- MIT License for open development 
