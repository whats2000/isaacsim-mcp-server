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

"""Browser live view: lifecycle, port handling and the HTTP surface.

Only Kit's APIs are faked here. The HTTP server and sockets are real, because
the bugs these guard against live in how a real bind fails and in what a real
request is allowed to do to the camera.
"""

from __future__ import annotations

import http.client
import socket
import sys
import threading
import types

import pytest
from isaac_sim_mcp_extension import live_view

HOST = "127.0.0.1"


class FakeApp:
    def __init__(self):
        self.callbacks = []
        self.ready = True

    def is_app_ready(self):
        return self.ready

    def get_update_event_stream(self):
        return self

    def create_subscription_to_pop(self, callback):
        self.callbacks.append(callback)
        return object()


class FakeTimeline:
    def is_playing(self):
        return False

    def is_stopped(self):
        return True

    def get_current_time(self):
        return 0.0


@pytest.fixture
def app(monkeypatch):
    fake = FakeApp()
    monkeypatch.setattr(sys.modules["omni.kit.app"], "get_app", lambda: fake, raising=False)
    monkeypatch.setattr(sys.modules["omni.timeline"], "get_timeline_interface", FakeTimeline, raising=False)
    yield fake
    live_view.stop()


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def serves(port: int) -> bool:
    try:
        conn = http.client.HTTPConnection(HOST, port, timeout=3)
        conn.request("GET", "/status")
        return conn.getresponse().status == 200
    except OSError:
        return False


# ── Lifecycle ──────────────────────────────────────────────────────────────────


def test_start_on_a_taken_port_keeps_the_running_view_serving(app):
    """Re-running start used to stop the old server first, then fail to bind."""
    port = free_port()
    live_view.start(port, HOST)
    with socket.socket() as blocker:
        blocker.bind((HOST, 0))
        blocker.listen(1)
        with pytest.raises(OSError):
            live_view.start(blocker.getsockname()[1], HOST)
        assert serves(port)


def test_start_on_a_free_port_moves_the_view(app):
    old_port, new_port = free_port(), free_port()
    live_view.start(old_port, HOST)
    live_view.start(new_port, HOST)
    assert serves(new_port)
    assert not serves(old_port)


def test_start_on_the_serving_endpoint_keeps_the_same_view(app):
    port = free_port()
    assert live_view.start(port, HOST) is live_view.start(port, HOST)


def test_stop_releases_the_port(app):
    port = free_port()
    live_view.start(port, HOST)
    live_view.stop()
    assert not serves(port)
    live_view.start(port, HOST)
    assert serves(port)


def test_restart_replaces_the_view_on_the_same_port(app):
    port = free_port()
    first = live_view.start(port, HOST)
    second = live_view.restart()
    assert second is not first
    assert serves(port)


def test_restart_without_a_running_view_starts_nothing(app):
    assert live_view.restart() is None


# ── POST /camera ───────────────────────────────────────────────────────────────


def post_camera(port: int, body: bytes, content_type="application/json") -> int:
    conn = http.client.HTTPConnection(HOST, port, timeout=3)
    headers = {"Content-Type": content_type} if content_type else {}
    conn.request("POST", "/camera", body=body, headers=headers)
    return conn.getresponse().status


@pytest.mark.parametrize(
    "body",
    [
        b'{"orbit": "nan"}',
        b'{"orbit": NaN}',
        b'{"tilt": Infinity}',
        b'{"zoom": -Infinity}',
        b'{"zoom": "1.25"}',
        b'{"orbit": true}',
        b'{"orbit": 20, "tilt": NaN}',
        b"[1]",
        b"not json",
    ],
)
def test_camera_rejects_bad_input_and_leaves_the_camera_alone(app, body):
    port = free_port()
    view = live_view.start(port, HOST)
    before = dict(view.orbit)
    assert post_camera(port, body) == 400
    assert view.orbit == before


def test_camera_applies_a_valid_orbit(app):
    port = free_port()
    view = live_view.start(port, HOST)
    assert post_camera(port, b'{"orbit": 20}') == 200
    assert view.orbit["yaw"] == 345.0  # default -35 + 20, wrapped to [0, 360)


def test_camera_orbit_cannot_overflow_to_infinity(app):
    port = free_port()
    view = live_view.start(port, HOST)
    for _ in range(2):
        assert post_camera(port, b'{"orbit": 1e308}') == 200
    assert view.orbit["yaw"] < 360.0


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", None])
def test_camera_refuses_what_a_foreign_page_can_send_without_preflight(app, content_type):
    """A cross-site fetch can only skip CORS preflight with these content types."""
    port = free_port()
    view = live_view.start(port, HOST)
    before = dict(view.orbit)
    assert post_camera(port, b'{"orbit": 20}', content_type) == 415
    assert view.orbit == before


def test_camera_accepts_json_with_a_charset(app):
    port = free_port()
    live_view.start(port, HOST)
    assert post_camera(port, b'{"orbit": 20}', "application/json; charset=utf-8") == 200


def test_page_buttons_send_the_content_type_the_server_requires(app):
    # No browser in the unit suite. Without this header every button gets a 415.
    assert b"'Content-Type':'application/json'" in live_view.PAGE


# ── /stream ────────────────────────────────────────────────────────────────────


def read_first_jpeg(port: int, out: list) -> None:
    conn = http.client.HTTPConnection(HOST, port, timeout=5)
    conn.request("GET", "/stream")
    data = b""
    resp = conn.getresponse()
    while b"JPEGBYTES" not in data:
        data += resp.read1(4096)
    out.append(data)
    conn.close()


def test_two_stream_clients_share_one_encode_per_frame(app, monkeypatch):
    """Each client encoding for itself cost 5.1 about 36% step speed at 4 clients."""
    encodes = []

    def fake_encode(frame):
        encodes.append(frame)
        return b"JPEGBYTES"

    monkeypatch.setattr(live_view, "_encode_jpeg", fake_encode)
    port = free_port()
    view = live_view.start(port, HOST)
    view.publish_frame("frame-1")

    received: list = []
    clients = [threading.Thread(target=read_first_jpeg, args=(port, received)) for _ in range(2)]
    for c in clients:
        c.start()
    for c in clients:
        c.join(timeout=5)

    assert len(received) == 2
    assert encodes == ["frame-1"]


def test_stop_ends_a_stream_waiting_for_its_next_frame(app, monkeypatch):
    monkeypatch.setattr(live_view, "_encode_jpeg", lambda frame: b"JPEGBYTES")
    port = free_port()
    view = live_view.start(port, HOST)
    view.publish_frame("frame-1")

    conn = http.client.HTTPConnection(HOST, port, timeout=5)
    conn.request("GET", "/stream")
    resp = conn.getresponse()
    data = b""
    while b"JPEGBYTES" not in data:
        data += resp.read1(4096)

    live_view.stop()
    # EOF, rather than this read hanging until the socket timeout.
    assert resp.read() is not None


# ── Replicator handling ────────────────────────────────────────────────────────


class FakeOrchestrator:
    def __init__(self, settings):
        self.settings = settings
        self.stopped_calls = 0

    def set_capture_on_play(self, value):
        self.settings["/omni/replicator/captureOnPlay"] = value

    def run(self):
        pass

    def stop(self):
        self.stopped_calls += 1

    def get_is_stopped(self):
        return False


class FakeRenderProduct:
    def destroy(self):
        pass


@pytest.fixture
def replicator(app, monkeypatch):
    """Fake Replicator plus a stage, reachable through the real update callback."""
    settings = {"/omni/replicator/captureOnPlay": True}
    created = []

    class Annotator:
        def attach(self, _rps):
            pass

        def detach(self):
            pass

        def get_data(self):
            return None

    def create_render_product(_camera, _resolution):
        created.append(1)
        return FakeRenderProduct()

    rep = types.SimpleNamespace(
        orchestrator=FakeOrchestrator(settings),
        create=types.SimpleNamespace(render_product=create_render_product),
        AnnotatorRegistry=types.SimpleNamespace(get_annotator=lambda _name: Annotator()),
    )
    prim = types.SimpleNamespace(IsValid=lambda: True, GetChildren=lambda: [])
    stage = types.SimpleNamespace(GetPrimAtPath=lambda _path: prim)
    context = types.SimpleNamespace(get_stage=lambda: stage, stage_id=1)
    context.get_stage_id = lambda: context.stage_id

    monkeypatch.setitem(sys.modules, "omni.replicator", types.ModuleType("omni.replicator"))
    monkeypatch.setitem(sys.modules, "omni.replicator.core", rep)
    sys.modules["omni.replicator"].core = rep
    monkeypatch.setattr(sys.modules["omni"], "replicator", sys.modules["omni.replicator"], raising=False)
    viewports = types.SimpleNamespace(set_camera_view=lambda **_kw: None)
    monkeypatch.setitem(sys.modules, "isaacsim.core.utils.viewports", viewports)
    monkeypatch.setattr(sys.modules["omni.usd"], "get_context", lambda: context, raising=False)
    monkeypatch.setattr(
        sys.modules["carb"].settings,
        "get_settings",
        lambda: types.SimpleNamespace(get=settings.get),
    )
    return types.SimpleNamespace(rep=rep, settings=settings, created=created, context=context)


def tick(app, count=1):
    for _ in range(count):
        app.callbacks[-1](None)


BOOT_TICKS = live_view.START_DELAY_FRAMES + 1


@pytest.mark.parametrize("original", [True, False])
def test_stop_puts_capture_on_play_back(app, replicator, original):
    replicator.settings["/omni/replicator/captureOnPlay"] = original
    live_view.start(free_port(), HOST)
    tick(app, BOOT_TICKS)
    assert replicator.settings["/omni/replicator/captureOnPlay"] is False
    live_view.stop()
    assert replicator.settings["/omni/replicator/captureOnPlay"] is original


def test_stop_stops_the_orchestrator_it_started(app, replicator):
    live_view.start(free_port(), HOST)
    tick(app, BOOT_TICKS)
    live_view.stop()
    assert replicator.rep.orchestrator.stopped_calls == 1


def test_stop_before_any_frame_leaves_replicator_alone(app, replicator):
    live_view.start(free_port(), HOST)
    live_view.stop()
    assert replicator.rep.orchestrator.stopped_calls == 0
    assert replicator.settings["/omni/replicator/captureOnPlay"] is True


def test_render_product_is_rebuilt_once_per_stage(app, replicator):
    live_view.start(free_port(), HOST)
    tick(app, BOOT_TICKS + 5)
    assert len(replicator.created) == 1
    replicator.context.stage_id = 2
    tick(app, 5)
    assert len(replicator.created) == 2


def test_render_product_waits_for_the_app_to_finish_loading(app, replicator):
    """The extension starts mid-boot, while Kit is still loading the rest of the app."""
    app.ready = False
    live_view.start(free_port(), HOST)
    tick(app, BOOT_TICKS * 3)
    assert replicator.created == []
    app.ready = True
    tick(app, BOOT_TICKS)
    assert len(replicator.created) == 1


def test_look_at_without_a_running_view_says_so(app):
    with pytest.raises(RuntimeError):
        live_view.look_at([1.0, 1.0, 1.0], [0.0, 0.0, 0.0])
