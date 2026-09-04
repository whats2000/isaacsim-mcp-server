#!/usr/bin/env python3
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
"""Live smoke test against a running Isaac Sim + MCP extension.

Connects to the extension socket (default localhost:8766), sends one command
per surface area, and prints pass/fail per check. Unit tests cannot cover any
of this: every check here needs a real physics step, a real USD stage, or a
real OmniGraph, and the fakes that would stand in for them are exactly what
let a wrong assumption reach a release.

Runs against **either** supported runtime and adapts:
    - Isaac Sim 6.0 (V6 adapter, PhysX or Newton) — additionally asserts the
      engine / isaacsim_version reporting fields.
    - Isaac Sim 5.1 (V5 adapter) — asserts those V6-only fields are absent,
      so a misdetected adapter fails the run instead of passing quietly.

Which runtime is in use is detected from simulation.get_state rather than
passed in, so pointing this at a port is enough.

Prerequisites:
    1. Isaac Sim running with the MCP extension enabled (isaac-sim.sh,
       isaac-sim.newton.sh, or scripts/run_isaac_sim.sh).
    2. The extension is running the code on disk. Kit reloads the extension
       itself when its files change; scripts/dev_mcp_server.sh does it on
       demand.

Usage:
    python scripts/smoke_test.py                 # default port 8766
    python scripts/smoke_test.py --port 8767     # a second instance

Both runtimes can be smoke-tested side by side by launching them on separate
ports:

    ./scripts/run_isaac_sim.sh
    ISAACSIM_ROOT=~/isaacsim-5.1.0 ./scripts/run_isaac_sim.sh \\
        --/exts/isaac.sim.mcp/server.port=8767
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
from typing import Any, Dict


def send(host: str, port: int, cmd_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect((host, port))
    try:
        payload = json.dumps({"type": cmd_type, "params": params}).encode("utf-8")
        sock.sendall(payload)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            try:
                return json.loads(b"".join(chunks).decode("utf-8"))
            except json.JSONDecodeError:
                continue
        return {"status": "error", "message": "Connection closed without complete JSON"}
    finally:
        sock.close()


def check(name: str, response: Dict[str, Any], assertion=None) -> bool:
    status = response.get("status")
    if status != "success":
        print(f"  [FAIL] {name}: {response.get('message')}", file=sys.stderr)
        return False
    if assertion is not None:
        ok, why = assertion(response.get("result", {}))
        if not ok:
            print(f"  [FAIL] {name}: {why}", file=sys.stderr)
            return False
    print(f"  [ OK ] {name}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()

    print(f"Connecting to Isaac Sim MCP extension at {args.host}:{args.port}...")

    results = []

    # 1. Which adapter answered? V6 reports engine + isaacsim_version;
    #    V5 has neither. That difference is the detector, and each runtime then
    #    gets the assertion that is true *for it* — V5 must not grow the V6
    #    fields, and V6 must not lose them.
    resp = send(args.host, args.port, "simulation.get_state", {})
    state = resp.get("result", {})
    is_v6 = "engine" in state or "isaacsim_version" in state
    engine = state.get("engine", "n/a")

    if is_v6:

        def _check_state(r: Dict[str, Any]) -> tuple[bool, str]:
            if r.get("engine") not in ("physx", "newton", "remotesim"):
                return False, f"unexpected engine: {r.get('engine')}"
            version = r.get("isaacsim_version")
            if not isinstance(version, str) or not version.startswith("6."):
                # A tuple repr ("('6.0.1', 'rc.7', ...)") lands here: 6.0's
                # get_version() returns an 8-tuple, and str()-ing it leaks a
                # Python repr to every MCP client.
                return False, f"unexpected isaacsim_version: {version!r}"
            return True, ""

        results.append(check("simulation.get_state shows engine + isaacsim_version", resp, _check_state))
    else:

        def _check_state_v5(r: Dict[str, Any]) -> tuple[bool, str]:
            leaked = [k for k in ("engine", "isaacsim_version") if k in r]
            if leaked:
                return False, f"V5 reported V6-only fields: {leaked}"
            for required in ("timeline_state", "physics_dt"):
                if required not in r:
                    return False, f"missing '{required}' in get_state"
            return True, ""

        results.append(check("simulation.get_state (V5 shape, no V6-only fields)", resp, _check_state_v5))

    print(f"        adapter={'V6' if is_v6 else 'V5'}, engine={engine}, version={state.get('isaacsim_version', 'n/a')}")

    # 2. Scene info round-trip
    resp = send(args.host, args.port, "scene.get_info", {})
    results.append(check("scene.get_info", resp))

    # 3. Create a cube and verify info
    send(args.host, args.port, "scene.clear", {})
    resp = send(
        args.host,
        args.port,
        "objects.create",
        {
            "object_type": "cube",
            "prim_path": "/World/SmokeCube",
            "size": 0.5,
            "position": [0.0, 0.0, 1.0],
        },
    )
    results.append(check("objects.create cube", resp))

    resp = send(args.host, args.port, "scene.get_prim_info", {"prim_path": "/World/SmokeCube"})

    def _is_cube(r: Dict[str, Any]) -> tuple[bool, str]:
        if r.get("type") != "Cube":
            return False, f"expected type=Cube, got {r.get('type')}"
        return True, ""

    results.append(check("scene.get_prim_info on cube", resp, _is_cube))

    # 4. Create a physics scene + ground plane, then step on a FROZEN timeline.
    #    step_simulation refuses to run while the timeline is playing (it is the
    #    step-only debug loop), so play is exercised separately below rather
    #    than before the step.
    resp = send(args.host, args.port, "simulation.set_physics", {"gravity": [0.0, 0.0, -9.81]})
    results.append(check("simulation.set_physics (creates PhysicsScene)", resp))

    resp = send(
        args.host,
        args.port,
        "simulation.step",
        {
            "num_steps": 30,
            "observe_prims": ["/World/SmokeCube"],
        },
    )

    def _stepped(r: Dict[str, Any]) -> tuple[bool, str]:
        if "prim_states" not in r:
            return False, "no prim_states in step response"
        states = r["prim_states"]
        if not states or "position" not in states[0]:
            return False, "no position observed for cube"
        return True, ""

    results.append(check("simulation.step with observe_prims (physics view read)", resp, _stepped))

    # play is the final-run mode, not part of the debug loop — exercise it on
    # its own, after the stepping is done.
    resp = send(args.host, args.port, "simulation.play", {})
    results.append(check("simulation.play", resp))

    resp = send(args.host, args.port, "simulation.stop", {})
    results.append(check("simulation.stop", resp))

    # step_simulation must refuse to run while the timeline is playing; that
    # guard is the contract the debug loop depends on, so assert it holds.
    send(args.host, args.port, "simulation.play", {})
    resp = send(args.host, args.port, "simulation.step", {"num_steps": 1})

    def _refused(r: Dict[str, Any]) -> tuple[bool, str]:
        return False, "step was accepted while the timeline was playing"

    refused = resp.get("status") == "error" and "running" in str(resp.get("message", ""))
    results.append(
        check(
            "simulation.step refuses to run while playing",
            {"status": "success"} if refused else resp,
            None if refused else _refused,
        )
    )
    send(args.host, args.port, "simulation.stop", {})

    # 4b. stop_simulation must reset the scene to spawn state: create a cube
    #     above the ground, play, step until it falls, stop, and verify the
    #     cube's world Z is back at its spawn value (not the fallen value).
    send(args.host, args.port, "scene.clear", {})
    resp = send(args.host, args.port, "simulation.set_physics", {"gravity": [0.0, 0.0, -9.81]})
    results.append(check("simulation.set_physics (reset test)", resp))

    spawn_z = 2.0
    resp = send(
        args.host,
        args.port,
        "objects.create",
        {
            "object_type": "cube",
            "prim_path": "/World/ResetCube",
            "size": 0.5,
            "position": [0.0, 0.0, spawn_z],
            # Without this the prim has no rigid body and cannot fall, so the
            # reset assertion below would pass its spawn Z trivially — while
            # proving nothing about stop_simulation.
            "physics_enabled": True,
        },
    )
    results.append(check("objects.create cube above ground (reset test)", resp))

    resp = send(
        args.host,
        args.port,
        "simulation.step",
        {
            "num_steps": 60,
            "observe_prims": ["/World/ResetCube"],
        },
    )

    def _fell(r: Dict[str, Any]) -> tuple[bool, str]:
        states = r.get("prim_states") or []
        if not states or "position" not in states[0]:
            return False, "no position observed for cube"
        z = states[0]["position"][2]
        if z >= spawn_z:
            return False, f"cube did not fall: z={z}"
        return True, ""

    results.append(check("simulation.step lets cube fall (reset test)", resp, _fell))

    resp = send(args.host, args.port, "simulation.stop", {})
    results.append(check("simulation.stop (reset test)", resp))

    resp = send(args.host, args.port, "scene.get_prim_info", {"prim_path": "/World/ResetCube"})

    def _back_at_spawn(r: Dict[str, Any]) -> tuple[bool, str]:
        # get_prim_info nests the transform, and names both frames explicitly:
        # {"transform": {"position_local": [...], "position_world": [...]}}.
        # There has never been a top-level position key. The cube sits directly
        # under the stage root, so either frame answers this; world is the one
        # that stays right if the check is ever moved under a parent.
        transform = r.get("transform") or {}
        position = transform.get("position_world") or transform.get("position_local")
        if not position:
            return False, f"no transform position in prim_info (keys: {sorted(transform)})"
        z = position[2]
        if abs(z - spawn_z) > 1e-3:
            return False, f"expected z~={spawn_z} after stop, got z={z}"
        return True, ""

    results.append(
        check(
            "scene.get_prim_info shows cube back at spawn Z after stop_simulation",
            resp,
            _back_at_spawn,
        )
    )

    # 5. URDF import round-trip is skipped because it requires a local URDF
    #    file in a known location — verified separately in the demo.

    # 6. Sensor smoke (camera only; lidar configs vary by Isaac Sim build).
    #    Both adapters implement this over different backends — V6 on
    #    isaacsim.sensors.experimental.rtx.RtxCamera, V5 on
    #    isaacsim.sensors.camera.Camera — so it is checked on both rather than
    #    gated behind a V6-only engine value.
    resp = send(
        args.host,
        args.port,
        "sensors.create_camera",
        {
            "prim_path": "/World/SmokeCamera",
            "position": [3.0, 0.0, 2.0],
            "resolution": [320, 240],
        },
    )
    backend = "experimental.rtx.RtxCamera" if is_v6 else "sensors.camera.Camera"
    results.append(check(f"sensors.create_camera ({backend})", resp))

    # 7. reload_script recompiles a matching Action-Graph ScriptNode (manual,
    #    exercises the ScriptNode-aware path added for the reload_script fix).
    #    Writes a controller file, wires it into an action graph as a
    #    ScriptNode, edits the file on disk, then calls reload_script and
    #    checks the response reports recompiled_nodes instead of re-exec'ing
    #    the file standalone.
    script_path = os.path.join(tempfile.gettempdir(), "smoke_test_scriptnode_controller.py")
    with open(script_path, "w") as f:
        f.write("def setup(db):\n    pass\n\ndef compute(db):\n    return True\n")

    resp = send(
        args.host,
        args.port,
        "graphs.create_action_graph",
        {
            "graph_path": "/World/SmokeActionGraph",
            "script_file": script_path,
        },
    )
    results.append(check("graphs.create_action_graph (script_file ScriptNode)", resp))

    resp = send(args.host, args.port, "simulation.play", {})
    results.append(check("simulation.play (scriptnode reload test)", resp))

    # Edit the file on disk — this is the change reload_script must pick up.
    with open(script_path, "w") as f:
        f.write(
            "def setup(db):\n"
            "    pass\n\n"
            "def compute(db):\n"
            "    # edited on disk to verify reload_script recompiles this node\n"
            "    return True\n"
        )

    resp = send(args.host, args.port, "simulation.reload_script", {"file_path": script_path})

    def _recompiled(r: Dict[str, Any]) -> tuple[bool, str]:
        if "recompiled_nodes" not in r:
            return False, "response missing 'recompiled_nodes' — fell back to standalone re-exec"
        if not r["recompiled_nodes"]:
            return False, "recompiled_nodes was empty — no ScriptNode matched"
        return True, ""

    results.append(
        check(
            "simulation.reload_script recompiles the ScriptNode (not standalone re-exec)",
            resp,
            _recompiled,
        )
    )

    resp = send(args.host, args.port, "simulation.stop", {})
    results.append(check("simulation.stop (scriptnode reload test)", resp))

    print()
    passed = sum(1 for r in results if r)
    adapter = "V6" if is_v6 else "V5"
    print(f"{passed}/{len(results)} checks passed ({adapter} adapter, engine={engine}).")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
