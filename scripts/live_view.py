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

"""Browser live view for a headless Isaac Sim.

Started by `./scripts/run_isaac_sim.sh --live-view` (Kit runs it via `--exec` once booted).
To start or restart it by hand, use the MCP execute_script tool:
    exec(open("/path/to/isaacsim-mcp-server/scripts/live_view.py").read())

Serves on 127.0.0.1:$ISAAC_LIVE_VIEW_PORT (default 18200). Reach it through an SSH tunnel
(`ssh -L 18200:127.0.0.1:18200 user@host`) or an authenticating reverse proxy:
  GET  /         page: live video, status, camera buttons
  GET  /stream   MJPEG feed
  GET  /status   JSON: timeline state, sim time, fps, prims under /World
  POST /camera   JSON: {"orbit": deg, "tilt": deg, "zoom": factor, "reset": true}

The camera is /OmniverseKit_Persp. Kit owns it, so it survives clear_scene. Frames render
whether the simulation is playing or stopped. To aim it from a prompt:
    import builtins; builtins._live_view["look_at"]([eye_x, eye_y, eye_z], [tx, ty, tz])
"""

import builtins
import io
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import carb
import numpy as np
import omni.kit.app
import omni.timeline
import omni.usd
from PIL import Image

HOST = os.environ.get("ISAAC_LIVE_VIEW_HOST", "127.0.0.1")
PORT = int(os.environ.get("ISAAC_LIVE_VIEW_PORT", "18200"))
CAMERA = "/OmniverseKit_Persp"
RESOLUTION = (960, 540)
JPEG_QUALITY = 80
DEFAULT_TARGET = [0.4, 0.0, 0.4]
DEFAULT_ORBIT = {"yaw": -35.0, "pitch": 22.0, "dist": 2.7}
START_DELAY_FRAMES = 60  # let Kit finish booting before creating the render product

old = getattr(builtins, "_live_view", None)
if old:
    old["stop"]()

tl = omni.timeline.get_timeline_interface()
S = {
    "running": True,
    "frame": None,
    "frame_id": 0,
    "fps": 0.0,
    "ticks": START_DELAY_FRAMES if old else 0,  # no boot delay when restarted by hand
    "stage_id": None,
    "rp": None,
    "ann": None,
    "target": list(DEFAULT_TARGET),
    "orbit": dict(DEFAULT_ORBIT),
    "pending_cam": True,
    "status": {},
    "_fps_t": time.time(),
    "_fps_n": 0,
}


def _log(msg):
    carb.log_warn(f"[live_view] {msg}")


def _eye():
    o, t = S["orbit"], S["target"]
    yaw, pitch = math.radians(o["yaw"]), math.radians(o["pitch"])
    return [
        t[0] + o["dist"] * math.cos(pitch) * math.cos(yaw),
        t[1] + o["dist"] * math.cos(pitch) * math.sin(yaw),
        t[2] + o["dist"] * math.sin(pitch),
    ]


def look_at(eye, target):
    """Point the live camera from `eye` at `target` (world metres)."""
    d = [eye[i] - target[i] for i in range(3)]
    dist = max(math.sqrt(sum(v * v for v in d)), 0.05)
    S["target"] = list(target)
    S["orbit"] = {
        "yaw": math.degrees(math.atan2(d[1], d[0])),
        "pitch": math.degrees(math.asin(max(-1.0, min(1.0, d[2] / dist)))),
        "dist": dist,
    }
    S["pending_cam"] = True


def _release_render_product():
    try:
        if S["ann"] is not None:
            S["ann"].detach()
        if S["rp"] is not None:
            S["rp"].destroy()
    except Exception as e:
        _log(f"release: {e}")
    S["ann"] = S["rp"] = None


def _ensure_render_product():
    """(Re)create the render product when missing or when the stage was replaced."""
    import omni.replicator.core as rep

    stage = omni.usd.get_context().get_stage()
    if stage is None or not stage.GetPrimAtPath(CAMERA).IsValid():
        return False
    sid = id(stage.GetRootLayer())
    if S["rp"] is not None and sid == S["stage_id"]:
        # Replicator only produces frames while its orchestrator runs; keep it running.
        if S["ticks"] % 120 == 0 and rep.orchestrator.get_is_stopped():
            rep.orchestrator.run()
        return True
    _release_render_product()
    # Decouple capture from the timeline so the view also updates while stopped.
    rep.orchestrator.set_capture_on_play(False)
    rep.orchestrator.run()
    S["rp"] = rep.create.render_product(CAMERA, RESOLUTION)
    S["ann"] = rep.AnnotatorRegistry.get_annotator("rgb")
    S["ann"].attach([S["rp"]])
    S["stage_id"] = sid
    S["pending_cam"] = True
    _log("render product ready")
    return True


def _on_update(_e):
    S["ticks"] += 1
    if S["ticks"] < START_DELAY_FRAMES:
        return
    try:
        if not _ensure_render_product():
            return
        if S["pending_cam"]:
            from isaacsim.core.utils.viewports import set_camera_view

            set_camera_view(eye=_eye(), target=S["target"], camera_prim_path=CAMERA)
            S["pending_cam"] = False
        d = S["ann"].get_data()
    except Exception as e:
        if S["ticks"] % 600 == 0:
            _log(f"update: {e}")
        return
    if d is not None and getattr(d, "size", 0):
        S["frame"] = np.asarray(d)[:, :, :3]
        S["frame_id"] += 1
        S["_fps_n"] += 1
    t = time.time()
    if t - S["_fps_t"] >= 1.0:
        S["fps"] = S["_fps_n"] / (t - S["_fps_t"])
        S["_fps_t"], S["_fps_n"] = t, 0
        stage = omni.usd.get_context().get_stage()
        world = stage.GetPrimAtPath("/World") if stage else None
        S["status"] = {
            "timeline": "playing" if tl.is_playing() else ("stopped" if tl.is_stopped() else "paused"),
            "sim_time": round(tl.get_current_time(), 2),
            "fps": round(S["fps"], 1),
            "prims": [c.GetName() for c in world.GetChildren()] if world and world.IsValid() else [],
        }


def _camera_cmd(cmd):
    if cmd.get("reset"):
        S["target"], S["orbit"] = list(DEFAULT_TARGET), dict(DEFAULT_ORBIT)
    o = S["orbit"]
    o["yaw"] += float(cmd.get("orbit", 0))
    o["pitch"] = max(-5.0, min(85.0, o["pitch"] + float(cmd.get("tilt", 0))))
    o["dist"] = max(0.3, min(30.0, o["dist"] * float(cmd.get("zoom", 1))))
    S["pending_cam"] = True


PAGE = b"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Isaac Sim Live</title>
<style>body{margin:0;background:#111;color:#eee;font:15px system-ui,sans-serif;padding:16px}
main{max-width:1100px;margin:0 auto}h1{font-size:18px;margin:0 0 10px}
img{width:100%;aspect-ratio:16/9;object-fit:contain;background:#000;border-radius:8px;display:block}
.row{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;align-items:center}
button{font:inherit;padding:6px 11px;border-radius:6px;border:1px solid #333;background:#222;color:#eee;cursor:pointer}
#s{color:#9aa3ad;font-size:13px;margin-top:8px;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
p{color:#9aa3ad;font-size:13px}</style>
<main><h1>Isaac Sim Live</h1><img id=v alt="Live view of the Isaac Sim scene">
<div class=row><button data-c='{"orbit":-20}'>Orbit left</button><button data-c='{"orbit":20}'>Orbit right</button>
<button data-c='{"tilt":8}'>Up</button><button data-c='{"tilt":-8}'>Down</button>
<button data-c='{"zoom":0.8}'>Zoom in</button><button data-c='{"zoom":1.25}'>Zoom out</button>
<button data-c='{"reset":true}'>Reset</button></div><div id=s>connecting...</div>
<p>Prompt your MCP client (Claude Code, Cursor, ...); the result shows up here.</p></main>
<script>const q=location.search,v=document.getElementById('v');
function connect(){v.src='stream'+q+(q?'&':'?')+'t='+Date.now()}v.onerror=()=>setTimeout(connect,3000);connect();
document.querySelectorAll('[data-c]').forEach(b=>b.onclick=()=>fetch('camera'+q,{method:'POST',body:b.dataset.c}));
setInterval(()=>fetch('status'+q).then(r=>r.json()).then(j=>{document.getElementById('s').textContent=
`${j.timeline} \\u00b7 t = ${j.sim_time.toFixed(1)} s \\u00b7 ${j.fps.toFixed(0)} fps \\u00b7 /World: ${j.prims.join(', ')||'empty'}`})
.catch(()=>{document.getElementById('s').textContent='Isaac Sim not reachable (restarting?)'}),1000);</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE)
        elif path == "/status":
            self._send(
                200,
                "application/json",
                json.dumps(S["status"] or {"timeline": "starting", "sim_time": 0, "fps": 0, "prims": []}).encode(),
            )
        elif path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = -1
            try:
                while S["running"]:
                    if S["frame_id"] == last or S["frame"] is None:
                        time.sleep(0.005)
                        continue
                    last = S["frame_id"]
                    buf = io.BytesIO()
                    Image.fromarray(S["frame"]).save(buf, "JPEG", quality=JPEG_QUALITY)
                    jpg = buf.getvalue()
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg))
                    self.wfile.write(jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path.split("?")[0] != "/camera":
            return self._send(404, "text/plain", b"not found")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            _camera_cmd(json.loads(self.rfile.read(n) or b"{}"))
            self._send(200, "application/json", b'{"ok": true}')
        except Exception as e:
            self._send(400, "application/json", json.dumps({"error": str(e)}).encode())

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


ThreadingHTTPServer.allow_reuse_address = True
_server = ThreadingHTTPServer((HOST, PORT), Handler)
_server.daemon_threads = True
threading.Thread(target=_server.serve_forever, daemon=True).start()


def _stop():
    S["running"] = False
    builtins._live_view["sub"] = None
    _server.shutdown()
    _server.server_close()
    _release_render_product()


builtins._live_view = {
    "stop": _stop,
    "look_at": look_at,
    "state": S,
    "sub": omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(_on_update),
}
_log(f"serving on http://{HOST}:{PORT}/")
