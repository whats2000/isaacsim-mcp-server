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

Opt-in: `./scripts/run_isaac_sim.sh --live-view`, or `ISAAC_LIVE_VIEW=1`. The extension starts it
in on_startup and stops it in on_shutdown. On a running Isaac Sim, through execute_script:
    from isaac_sim_mcp_extension import live_view
    live_view.start(18200)          # or live_view.stop() / live_view.restart()

Serves on 127.0.0.1 on the port the extension resolves (default 18200, one per MCP port). Reach it
through an SSH tunnel (`ssh -L 18200:127.0.0.1:18200 user@host`) or an authenticating reverse proxy:
  GET  /         page: live video, status, camera buttons
  GET  /stream   MJPEG feed
  GET  /status   JSON: timeline state, sim time, fps, prims under /World
  POST /camera   JSON: {"orbit": deg, "tilt": deg, "zoom": factor, "reset": true}

The camera is /OmniverseKit_Persp. Kit owns it, so it survives clear_scene. Frames render
whether the simulation is playing or stopped. To aim it from a prompt:
    live_view.look_at([eye_x, eye_y, eye_z], [tx, ty, tz])
"""

from __future__ import annotations

import io
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import carb
import numpy as np
import omni.kit.app
import omni.timeline
import omni.usd

CAMERA = "/OmniverseKit_Persp"
RESOLUTION = (960, 540)
JPEG_QUALITY = 80
DEFAULT_TARGET = [0.4, 0.0, 0.4]
DEFAULT_ORBIT = {"yaw": -35.0, "pitch": 22.0, "dist": 2.7}
START_DELAY_FRAMES = 60  # frames to wait after "app ready" before creating the render product
CAPTURE_ON_PLAY = "/omni/replicator/captureOnPlay"

# Survives importlib.reload (dev_mcp_server.sh), which would otherwise lose the handle
# to a server still holding the port.
_active: "LiveView | None" = globals().get("_active")


def _log(msg):
    carb.log_warn(f"[live_view] {msg}")


def _encode_jpeg(frame) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(frame).save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _finite_number(cmd, key, default):
    value = cmd.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{key} must be a finite number")
    return float(value)


class LiveView:
    def __init__(self, server, endpoint):
        self.server = server
        self.endpoint = endpoint
        self.running = True
        self.frame = None
        self.frame_id = 0
        self.fps = 0.0
        self.ticks = 0
        self.stage_id = None
        self.rp = None
        self.ann = None
        self.target = list(DEFAULT_TARGET)
        self.orbit = dict(DEFAULT_ORBIT)
        self.pending_cam = True
        self.status = {}
        self.sub = None
        self._timeline = omni.timeline.get_timeline_interface()
        self._replicator_started = False
        self._capture_on_play = None
        self._fps_t = time.time()
        self._fps_n = 0
        self._frame_ready = threading.Condition()
        self._encode_lock = threading.Lock()
        self._jpeg = None
        self._jpeg_id = 0

    def start(self):
        self.server.view = self
        threading.Thread(target=self.server.serve_forever, args=(0.1,), daemon=True).start()
        self.sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self._on_update)

    def stop(self):
        self.sub = None
        with self._frame_ready:
            self.running = False
            self._frame_ready.notify_all()
        self.server.shutdown()
        self.server.server_close()
        self._release_replicator()

    def _eye(self):
        o, t = self.orbit, self.target
        yaw, pitch = math.radians(o["yaw"]), math.radians(o["pitch"])
        return [
            t[0] + o["dist"] * math.cos(pitch) * math.cos(yaw),
            t[1] + o["dist"] * math.cos(pitch) * math.sin(yaw),
            t[2] + o["dist"] * math.sin(pitch),
        ]

    def look_at(self, eye, target):
        """Point the live camera from `eye` at `target` (world metres)."""
        d = [eye[i] - target[i] for i in range(3)]
        dist = max(math.sqrt(sum(v * v for v in d)), 0.05)
        self.target = list(target)
        self.orbit = {
            "yaw": math.degrees(math.atan2(d[1], d[0])),
            "pitch": math.degrees(math.asin(max(-1.0, min(1.0, d[2] / dist)))),
            "dist": dist,
        }
        self.pending_cam = True

    def apply_camera(self, cmd):
        """Apply a POST /camera command. Nothing changes unless all of it is valid."""
        if not isinstance(cmd, dict):
            raise ValueError("expected a JSON object")
        orbit = _finite_number(cmd, "orbit", 0)
        tilt = _finite_number(cmd, "tilt", 0)
        zoom = _finite_number(cmd, "zoom", 1)
        if cmd.get("reset"):
            self.target, self.orbit = list(DEFAULT_TARGET), dict(DEFAULT_ORBIT)
        o = self.orbit
        o["yaw"] = (o["yaw"] + orbit) % 360.0
        o["pitch"] = max(-5.0, min(85.0, o["pitch"] + tilt))
        o["dist"] = max(0.3, min(30.0, o["dist"] * zoom))
        self.pending_cam = True

    def publish_frame(self, frame):
        with self._frame_ready:
            self.frame = frame
            self.frame_id += 1
            self._frame_ready.notify_all()

    def next_jpeg(self, last_id):
        """Block until a frame newer than `last_id`, and return (jpeg, id); (None, id) once stopped.

        Clients share one encode per frame. Encoding runs on the HTTP threads and holds the GIL
        against Kit's main thread: on 5.1, where a step renders a frame, four clients encoding
        separately slowed step_simulation by about 36%. Encoding happens outside _frame_ready so
        publish_frame on the main thread never waits for it.
        """
        with self._frame_ready:
            while self.running and (self.frame is None or self.frame_id == last_id):
                self._frame_ready.wait(0.5)
            if not self.running:
                return None, last_id
            frame, frame_id = self.frame, self.frame_id
        with self._encode_lock:
            if self._jpeg_id < frame_id:
                self._jpeg, self._jpeg_id = _encode_jpeg(frame), frame_id
            return self._jpeg, self._jpeg_id

    def _release_render_product(self):
        try:
            if self.ann is not None:
                self.ann.detach()
            if self.rp is not None:
                self.rp.destroy()
        except Exception as e:
            _log(f"release: {e}")
        self.ann = self.rp = None

    def _release_replicator(self):
        self._release_render_product()
        if not self._replicator_started:
            return
        try:
            import omni.replicator.core as rep

            rep.orchestrator.stop()
            if self._capture_on_play is not None:
                rep.orchestrator.set_capture_on_play(self._capture_on_play)
        except Exception as e:
            _log(f"release: {e}")
        self._replicator_started = False

    def _ensure_render_product(self):
        """(Re)create the render product when missing or when the stage was replaced."""
        import omni.replicator.core as rep

        context = omni.usd.get_context()
        stage = context.get_stage()
        if stage is None or not stage.GetPrimAtPath(CAMERA).IsValid():
            return False
        sid = context.get_stage_id()
        if self.rp is not None and sid == self.stage_id:
            # Replicator only produces frames while its orchestrator runs; keep it running.
            if self.ticks % 120 == 0 and rep.orchestrator.get_is_stopped():
                rep.orchestrator.run()
            return True
        self._release_render_product()
        if not self._replicator_started:
            self._capture_on_play = carb.settings.get_settings().get(CAPTURE_ON_PLAY)
            self._replicator_started = True
        # Decouple capture from the timeline so the view also updates while stopped. This has to
        # come before run(): under the default captureOnPlay, run() starts the timeline (see
        # _request_render_frame in adapters/v6.py), which would break the step-only debug loop.
        rep.orchestrator.set_capture_on_play(False)
        rep.orchestrator.run()
        self.rp = rep.create.render_product(CAMERA, RESOLUTION)
        self.ann = rep.AnnotatorRegistry.get_annotator("rgb")
        self.ann.attach([self.rp])
        self.stage_id = sid
        self.pending_cam = True
        _log("render product ready")
        return True

    def _on_update(self, _e):
        # The extension starts mid-boot. Creating the render product while Kit is still loading
        # the app is a race we do not need: a 6.0.1 boot once stalled in rendering right there,
        # before "app ready", and never recovered (1 in 18 boots, not proven to be the cause).
        if not omni.kit.app.get_app().is_app_ready():
            return
        self.ticks += 1
        if self.ticks < START_DELAY_FRAMES:
            return
        try:
            if not self._ensure_render_product():
                return
            if self.pending_cam:
                from isaacsim.core.utils.viewports import set_camera_view

                set_camera_view(eye=self._eye(), target=self.target, camera_prim_path=CAMERA)
                self.pending_cam = False
            d = self.ann.get_data()
        except Exception as e:
            if self.ticks % 600 == 0:
                _log(f"update: {e}")
            return
        if d is not None and getattr(d, "size", 0):
            self.publish_frame(np.asarray(d)[:, :, :3])
            self._fps_n += 1
        t = time.time()
        if t - self._fps_t >= 1.0:
            self.fps = self._fps_n / (t - self._fps_t)
            self._fps_t, self._fps_n = t, 0
            stage = omni.usd.get_context().get_stage()
            world = stage.GetPrimAtPath("/World") if stage else None
            tl = self._timeline
            self.status = {
                "timeline": "playing" if tl.is_playing() else ("stopped" if tl.is_stopped() else "paused"),
                "sim_time": round(tl.get_current_time(), 2),
                "fps": round(self.fps, 1),
                "prims": [c.GetName() for c in world.GetChildren()] if world and world.IsValid() else [],
            }


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
document.querySelectorAll('[data-c]').forEach(b=>b.onclick=()=>fetch('camera'+q,{method:'POST',headers:{'Content-Type':'application/json'},body:b.dataset.c}));
setInterval(()=>fetch('status'+q).then(r=>r.json()).then(j=>{document.getElementById('s').textContent=
`${j.timeline} \\u00b7 t = ${j.sim_time.toFixed(1)} s \\u00b7 ${j.fps.toFixed(0)} fps \\u00b7 /World: ${j.prims.join(', ')||'empty'}`})
.catch(()=>{document.getElementById('s').textContent='Isaac Sim not reachable (restarting?)'}),1000);</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        view = self.server.view
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE)
        elif path == "/status":
            self._send(
                200,
                "application/json",
                json.dumps(view.status or {"timeline": "starting", "sim_time": 0, "fps": 0, "prims": []}).encode(),
            )
        elif path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = 0
            try:
                while True:
                    jpg, last = view.next_jpeg(last)
                    if jpg is None:
                        break
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
            body = self.rfile.read(n)
            # A page on another site can only reach this without a CORS preflight, which this
            # server does not answer, by sending a non-JSON content type. Compared to checking
            # Origin against Host, this also keeps working behind a proxy that rewrites Host.
            if self.headers.get_content_type() != "application/json":
                return self._send(415, "application/json", b'{"error": "expected application/json"}')
            self.server.view.apply_camera(json.loads(body or b"{}"))
            self._send(200, "application/json", b'{"ok": true}')
        except Exception as e:
            self._send(400, "application/json", json.dumps({"error": str(e)}).encode())

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start(port, host="127.0.0.1"):
    """Serve on (host, port), replacing any running view. Raises OSError if the port is taken."""
    global _active
    if _active is not None and _active.endpoint == (host, port):
        return _active
    # Bind first: if this fails, the view already running keeps serving.
    server = ThreadingHTTPServer((host, port), Handler)
    stop()
    _active = LiveView(server, (host, port))
    _active.start()
    _log(f"serving on http://{host}:{port}/")
    return _active


def stop():
    global _active
    if _active is not None:
        _active.stop()
        _active = None


def restart():
    """Stop the running view and start a new one on its endpoint, or do nothing if none is running."""
    if _active is None:
        return None
    host, port = _active.endpoint
    stop()
    return start(port, host)


def look_at(eye, target):
    """Point the live camera from `eye` at `target` (world metres)."""
    if _active is None:
        raise RuntimeError("live view is not running; call live_view.start(port) first")
    _active.look_at(eye, target)
