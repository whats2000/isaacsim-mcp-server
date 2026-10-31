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

"""Unit tests for the socket host/port resolution in ``extension.py``.

The manifest ``[settings]`` block lands under the extension folder name
(``/exts/isaac.sim.mcp_extension/``, port key ``server.socket``); reading the
wrong prefix silently falls through to the defaults, which is a bug a live
smoke test on the default port cannot catch. These lock the resolution order.
"""

from __future__ import annotations

import pytest
from isaac_sim_mcp_extension import live_view
from isaac_sim_mcp_extension.extension import (
    MCPExtension,
    _env_int,
    _live_view_enabled,
    _resolve_endpoint,
    _resolve_live_view_endpoint,
    _start_live_view,
)

# Setting paths, named so the ordering assertions below read clearly.
LEGACY_PORT = "/exts/isaac.sim.mcp/server.port"
LEGACY_HOST = "/exts/isaac.sim.mcp/server.host"
MANIFEST_PORT = "/exts/isaac.sim.mcp_extension/server.port"
MANIFEST_SOCKET = "/exts/isaac.sim.mcp_extension/server.socket"
MANIFEST_HOST = "/exts/isaac.sim.mcp_extension/server.host"
LIVE_VIEW_ENABLED = "/exts/isaac.sim.mcp_extension/live_view/enabled"
LIVE_VIEW_PORT = "/exts/isaac.sim.mcp_extension/live_view/port"
LIVE_VIEW_HOST = "/exts/isaac.sim.mcp_extension/live_view/host"


class FakeSettings:
    """Stand-in for carb settings: ``.get`` returns None for unset paths."""

    def __init__(self, values: dict | None = None):
        self._values = values or {}

    def get(self, key):
        return self._values.get(key)


@pytest.fixture(autouse=True)
def _clear_endpoint_env(monkeypatch):
    """Keep the ambient environment from leaking into the resolution tests."""
    monkeypatch.delenv("ISAAC_MCP_PORT", raising=False)
    monkeypatch.delenv("ISAAC_MCP_HOST", raising=False)
    monkeypatch.delenv("ISAAC_LIVE_VIEW", raising=False)
    monkeypatch.delenv("ISAAC_LIVE_VIEW_PORT", raising=False)
    monkeypatch.delenv("ISAAC_LIVE_VIEW_HOST", raising=False)


def test_env_int_reads_valid_value(monkeypatch):
    monkeypatch.setenv("ISAAC_MCP_PORT", "8767")
    assert _env_int("ISAAC_MCP_PORT") == 8767


def test_env_int_ignores_malformed_value(monkeypatch):
    monkeypatch.setenv("ISAAC_MCP_PORT", "not-a-number")
    assert _env_int("ISAAC_MCP_PORT") is None


def test_env_int_ignores_unset_value():
    assert _env_int("ISAAC_MCP_PORT") is None


def test_defaults_when_nothing_set():
    assert _resolve_endpoint(FakeSettings()) == ("localhost", 8766)


def test_manifest_socket_key_supplies_port():
    # The regression: the manifest carries the port under `server.socket`, and
    # the old code read `server.port` under the wrong prefix, so this fell
    # through to 8766 even though the manifest asked for 9000.
    host, port = _resolve_endpoint(FakeSettings({MANIFEST_SOCKET: 9000}))
    assert (host, port) == ("localhost", 9000)


def test_manifest_port_key_also_supplies_port():
    # `server.port` under the manifest prefix is read before `server.socket`;
    # both are honoured so a future manifest can use either key name.
    host, port = _resolve_endpoint(FakeSettings({MANIFEST_PORT: 9100}))
    assert (host, port) == ("localhost", 9100)


def test_manifest_host_is_read():
    host, port = _resolve_endpoint(FakeSettings({MANIFEST_HOST: "0.0.0.0"}))
    assert (host, port) == ("0.0.0.0", 8766)


def test_env_vars_used_when_settings_absent(monkeypatch):
    monkeypatch.setenv("ISAAC_MCP_PORT", "8767")
    monkeypatch.setenv("ISAAC_MCP_HOST", "127.0.0.1")
    assert _resolve_endpoint(FakeSettings()) == ("127.0.0.1", 8767)


def test_malformed_env_port_falls_through_to_default(monkeypatch):
    monkeypatch.setenv("ISAAC_MCP_PORT", "garbage")
    assert _resolve_endpoint(FakeSettings()) == ("localhost", 8766)


def test_legacy_prefix_wins_over_manifest_and_env(monkeypatch):
    # The launcher passes the legacy prefix on the Kit command line; it must
    # take precedence over both the manifest block and the environment.
    monkeypatch.setenv("ISAAC_MCP_PORT", "3333")
    monkeypatch.setenv("ISAAC_MCP_HOST", "env-host")
    settings = FakeSettings(
        {
            LEGACY_PORT: 8766,
            LEGACY_HOST: "localhost",
            MANIFEST_SOCKET: 9000,
            MANIFEST_HOST: "manifest-host",
        }
    )
    assert _resolve_endpoint(settings) == ("localhost", 8766)


def test_manifest_wins_over_env():
    # No legacy override present: the manifest still beats the environment.
    settings = FakeSettings({MANIFEST_SOCKET: 9000, MANIFEST_HOST: "manifest-host"})
    host, port = _resolve_endpoint(settings)
    assert (host, port) == ("manifest-host", 9000)


# ── Live view ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "settings, env, expected",
    [
        ({}, None, False),
        ({}, "0", False),
        ({}, "false", False),
        ({}, "", False),
        ({}, "1", True),
        ({}, "true", True),
        ({LIVE_VIEW_ENABLED: True}, None, True),
        ({LIVE_VIEW_ENABLED: True}, "0", True),
    ],
)
def test_live_view_is_opt_in(monkeypatch, settings, env, expected):
    if env is not None:
        monkeypatch.setenv("ISAAC_LIVE_VIEW", env)
    assert _live_view_enabled(FakeSettings(settings)) is expected


def test_live_view_default_endpoint_is_localhost_18200():
    assert _resolve_live_view_endpoint(FakeSettings(), 8766) == ("127.0.0.1", 18200)


def test_second_instance_gets_its_own_live_view_port():
    """A fixed port made the second instance's live view fail to bind."""
    assert _resolve_live_view_endpoint(FakeSettings(), 8767) == ("127.0.0.1", 18201)


def test_live_view_port_precedence(monkeypatch):
    monkeypatch.setenv("ISAAC_LIVE_VIEW_PORT", "18300")
    assert _resolve_live_view_endpoint(FakeSettings(), 8766)[1] == 18300
    assert _resolve_live_view_endpoint(FakeSettings({LIVE_VIEW_PORT: 18400}), 8766)[1] == 18400


def test_live_view_host_precedence(monkeypatch):
    monkeypatch.setenv("ISAAC_LIVE_VIEW_HOST", "0.0.0.0")
    assert _resolve_live_view_endpoint(FakeSettings(), 8766)[0] == "0.0.0.0"
    assert _resolve_live_view_endpoint(FakeSettings({LIVE_VIEW_HOST: "10.0.0.5"}), 8766)[0] == "10.0.0.5"


def test_live_view_stays_off_unless_opted_in(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("live view started without opt-in")

    monkeypatch.setattr(live_view, "start", fail)
    _start_live_view(FakeSettings(), 8766)


def test_live_view_bind_failure_is_reported_and_does_not_stop_startup(monkeypatch):
    """The MCP socket must still come up when only the live view cannot start."""
    errors = []
    monkeypatch.setattr("carb.log_error", errors.append)

    def taken(_port, _host):
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(live_view, "start", taken)
    _start_live_view(FakeSettings({LIVE_VIEW_ENABLED: True}), 8766)
    assert len(errors) == 1
    assert "18200" in errors[0]
    assert "ISAAC_LIVE_VIEW_PORT" in errors[0]


def test_extension_shutdown_stops_the_live_view(monkeypatch):
    stops = []
    monkeypatch.setattr(live_view, "stop", lambda: stops.append(1))
    MCPExtension().on_shutdown()
    assert stops == [1]
