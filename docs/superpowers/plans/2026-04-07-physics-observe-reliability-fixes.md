# Physics & Observe Reliability Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 bugs that cause ScriptNode scripts to fail and step_simulation to return stale/incorrect observation data.

**Architecture:** All fixes are in the Isaac Sim extension adapter layer. Bug 1 adds `_ensure_physics_world` to the base class so future adapters don't crash. Bug 2 switches velocity reads from USD attributes to the PhysX tensor API. Bug 3 makes joint position reads use the physics tensor API with a USD fallback. Bug 4 adds `_ensure_physics_world()` to `reload_script`.

**Tech Stack:** Python, USD (pxr), Isaac Sim 5.1 APIs (`isaacsim.core`, `omni.physx`)

---

### Task 1: Add `_ensure_physics_world()` to base adapter class

**Files:**
- Modify: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/base.py:269` (Simulation section)
- Modify: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py:840-857` (move logic, keep override)

The `graphs.py` handler calls `adapter._ensure_physics_world()` but this method only exists on `IsaacAdapterV5`. Any future adapter (v4, v6) would crash with `AttributeError`.

- [ ] **Step 1: Add default implementation to base class**

In `base.py`, add this method to `IsaacAdapterBase` before the `play()` abstract method (around line 269):

```python
    def _ensure_physics_world(self) -> None:
        """Ensure a World with initialised physics exists.

        Called by play() and create_action_graph() to guarantee that
        SingleArticulation.initialize() works inside ScriptNode scripts.

        The default implementation uses isaacsim.core.api.World (Isaac Sim 5.x).
        Override in version-specific adapters if the API differs.
        """
        try:
            from isaacsim.core.api import World

            world = World.instance()
            if world is None:
                world = World(
                    physics_dt=1.0 / 60.0,
                    rendering_dt=1.0 / 60.0,
                    stage_units_in_meters=1.0,
                )
            if world.physics_sim_view is None:
                world.initialize_physics()
        except ImportError:
            pass  # Non-v5 runtimes may not have isaacsim.core.api
```

- [ ] **Step 2: Remove duplicate from v5.py**

In `v5.py`, delete lines 840-857 (the `_ensure_physics_world` method). The v5 adapter inherits the base implementation which uses the same `isaacsim.core.api.World` API.

- [ ] **Step 3: Verify graphs.py still calls it correctly**

Open `isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/graphs.py` and confirm line 58 still reads:
```python
adapter._ensure_physics_world()
```
No change needed — it calls through the adapter instance which now resolves to the base class method.

- [ ] **Step 4: Verify play() still calls it**

Open `v5.py` and confirm the `play()` method (now around line 840 after deletion) still reads:
```python
    def play(self) -> None:
        import omni.timeline

        self._ensure_physics_world()
        omni.timeline.get_timeline_interface().play()
```

- [ ] **Step 5: Commit**

```bash
git add isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/base.py isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py
git commit -m "fix: move _ensure_physics_world to base adapter class"
```

---

### Task 2: Fix stale velocity data in `observe_prims`

**Files:**
- Modify: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py:668-680` (`get_physics_state` velocity reading)

`get_physics_state()` reads velocities via `RigidBodyAPI.GetVelocityAttr().Get()` without a time code. In USD, `.Get()` without a time code returns the **authored default** (usually 0), not the physics-computed value at the current frame. The PhysX interface provides a reliable runtime API.

- [ ] **Step 1: Replace USD velocity reads with PhysX rigid body API**

In `v5.py`, replace the velocity reading block in `get_physics_state()` (lines 668-680):

```python
        # Get velocities from PhysX runtime API (not USD attributes which may be stale)
        if has_rb:
            try:
                import omni.physx

                physx = omni.physx.get_physx_interface()
                rb_data = physx.get_rigidbody_transformation(prim_path)
                if rb_data and rb_data.get("ret_val", False):
                    vel = rb_data.get("linear_velocity", (0.0, 0.0, 0.0))
                    ang_vel = rb_data.get("angular_velocity", (0.0, 0.0, 0.0))
                    result["linear_velocity"] = [float(vel[0]), float(vel[1]), float(vel[2])]
                    result["angular_velocity"] = [float(ang_vel[0]), float(ang_vel[1]), float(ang_vel[2])]
                else:
                    result["linear_velocity"] = [0.0, 0.0, 0.0]
                    result["angular_velocity"] = [0.0, 0.0, 0.0]
            except Exception:
                result["linear_velocity"] = [0.0, 0.0, 0.0]
                result["angular_velocity"] = [0.0, 0.0, 0.0]
```

- [ ] **Step 2: Also fix position reading in `observe_prims` to use PhysX**

In the `step()` method (around line 896-898), the position is read via `get_prim_transform()` which uses `GetLocalTransformation()`. This works for simple scenes but may miss physics-driven transforms on nested prims. Update the observe block to also try PhysX:

```python
                state: Dict[str, Any] = {"prim_path": path}
                # Prefer PhysX runtime position for rigid bodies (always current)
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    try:
                        import omni.physx

                        physx = omni.physx.get_physx_interface()
                        rb_data = physx.get_rigidbody_transformation(path)
                        if rb_data and rb_data.get("ret_val", False):
                            pos = rb_data["position"]
                            state["position"] = [float(pos[0]), float(pos[1]), float(pos[2])]
                        else:
                            transform = self.get_prim_transform(path)
                            state["position"] = transform.get("position", [0, 0, 0])
                    except Exception:
                        transform = self.get_prim_transform(path)
                        state["position"] = transform.get("position", [0, 0, 0])
                else:
                    transform = self.get_prim_transform(path)
                    state["position"] = transform.get("position", [0, 0, 0])
```

- [ ] **Step 3: Test by running step_simulation with a physics-enabled cube**

Set up a scene with a cube that has physics, step, and verify velocity is non-zero while falling:

```bash
# Via MCP: create physics scene, create cube with physics_enabled=true at height,
# play, step 10, observe — velocity Z should be negative (falling).
```

- [ ] **Step 4: Commit**

```bash
git add isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py
git commit -m "fix: use PhysX runtime API for observe velocity and position data"
```

---

### Task 3: Fix `observe_joints` reading stale USD drive targets

**Files:**
- Modify: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py:484-521` (`get_joint_positions`)

`get_joint_positions()` tries `SingleArticulation.initialize()` then falls back to reading USD `DriveAPI.GetTargetPositionAttr()`. The fallback returns **authored target values** (what the user commanded), not **actual physics-computed joint angles**. When `initialize()` fails (no physics sim view), the fallback silently returns wrong data.

- [ ] **Step 1: Call `_ensure_physics_world()` before articulation init**

In `get_joint_positions()` (line 484), add `_ensure_physics_world()` before trying to initialize the articulation:

```python
    def get_joint_positions(self, prim_path: str) -> List[float]:
        from isaacsim.core.prims import SingleArticulation

        # Ensure physics is initialized so SingleArticulation.initialize() works
        self._ensure_physics_world()

        art = SingleArticulation(prim_path=prim_path)
        try:
            art.initialize()
            positions = art.get_joint_positions()
            if positions is not None:
                return positions.tolist()
        except Exception:
            pass

        # Fallback: read drive target positions from USD
        # WARNING: these are authored targets, not actual physics positions
        from pxr import Usd, UsdPhysics
        ...  # rest unchanged
```

- [ ] **Step 2: Apply same fix to `_get_joint_names()` and `get_joint_config()`**

Add `self._ensure_physics_world()` at the top of `_get_joint_names()` (line 459) and `get_joint_config()` (line 523) before the `SingleArticulation` usage:

```python
    def _get_joint_names(self, prim_path: str) -> List[str]:
        from isaacsim.core.prims import SingleArticulation

        self._ensure_physics_world()
        art = SingleArticulation(prim_path=prim_path)
        ...
```

```python
    def get_joint_config(self, prim_path: str) -> Dict[str, Any]:
        from isaacsim.core.prims import SingleArticulation
        from pxr import Usd, UsdPhysics

        self._ensure_physics_world()
        ...
```

- [ ] **Step 3: Commit**

```bash
git add isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py
git commit -m "fix: ensure physics world before articulation reads in observe_joints"
```

---

### Task 4: Add `_ensure_physics_world()` to `reload_script`

**Files:**
- Modify: `isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py:1000-1054` (`reload_script`)

Scripts loaded via `reload_script` that call `SingleArticulation.initialize()` fail if physics isn't ready. The `create_action_graph` and `play` handlers both call `_ensure_physics_world()`, but `reload_script` doesn't.

- [ ] **Step 1: Add `_ensure_physics_world()` call before script execution**

In `reload_script()`, add the call just before the `exec(code, local_ns)` line (around line 1054):

```python
                local_ns = {
                    "omni": omni,
                    "carb": carb,
                    "Usd": Usd,
                    "UsdGeom": UsdGeom,
                    "Sdf": Sdf,
                    "Gf": Gf,
                    "__file__": file_path,
                }
                self._ensure_physics_world()
                exec(code, local_ns)
```

- [ ] **Step 2: Also add to `execute_script()`**

In `execute_script()` (line 960), add the same call before `exec(code, local_ns)` (line 979):

```python
        try:
            self._ensure_physics_world()
            exec(code, local_ns)
```

- [ ] **Step 3: Commit**

```bash
git add isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py
git commit -m "fix: ensure physics world before reload_script and execute_script"
```

---

## Post-Implementation Verification

After all 4 tasks, verify end-to-end by running the Franka pick-and-place demo:

1. Restart Isaac Sim (loads updated extension)
2. Set up scene: `create_physics_scene`, `create_robot(frankafr3)`, tables, cube
3. `create_action_graph(script_file="demo/franka_pick_place.py")`
4. Press Play in Isaac Sim UI — robot should execute full pick-and-place
5. `step_simulation` with `observe_prims` — velocities should be non-zero during motion
6. `step_simulation` with `observe_joints` — joint values should match actual physics state
