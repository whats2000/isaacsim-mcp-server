# MIT License
#
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

"""Physics-engine selection in scripts/lib/isaac_launcher.sh.

Isaac Sim ships one launcher per backend (isaac-sim.sh for PhysX,
isaac-sim.newton.sh for Newton). These tests run the real bash helper against a
fake install tree, so a regression in engine selection or argument forwarding
fails here rather than at launch time.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(REPO_ROOT, "scripts", "lib", "isaac_launcher.sh")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _fake_install(tmp_path, launchers):
    """Create an Isaac Sim install root containing only the given launcher names."""
    root = tmp_path / "isaacsim"
    root.mkdir()
    for name in launchers:
        script = root / name
        script.write_text("#!/bin/bash\n")
        script.chmod(0o755)
    return str(root)


def _resolve(root, *args, env=None):
    """Run isaac_resolve_launcher and report (rc, engine, launcher, passthru, stderr)."""
    script = f"""
    set -euo pipefail
    source {LIB}
    if isaac_resolve_launcher "$@"; then
        echo "ENGINE=$ISAACSIM_ENGINE"
        echo "LAUNCHER=$(basename "$ISAAC_SIM_SH")"
        echo "ARGS=${{ISAAC_PASSTHRU_ARGS[*]-}}"
    else
        exit 1
    fi
    """
    proc = subprocess.run(
        ["bash", "-c", script, "bash", root, *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    fields = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines() if "=" in line)
    return proc.returncode, fields, proc.stderr


@pytest.fixture
def full_install(tmp_path):
    """A 6.0-style install: both PhysX and Newton launchers present."""
    return _fake_install(tmp_path, ["isaac-sim.sh", "isaac-sim.newton.sh"])


def test_defaults_to_physx(full_install):
    rc, out, _ = _resolve(full_install)
    assert rc == 0
    assert out["ENGINE"] == "physx"
    assert out["LAUNCHER"] == "isaac-sim.sh"


@pytest.mark.parametrize("args", [("--newton",), ("--engine", "newton"), ("--engine=newton",)])
def test_newton_selected_by_flag(full_install, args):
    rc, out, _ = _resolve(full_install, *args)
    assert rc == 0
    assert out["ENGINE"] == "newton"
    assert out["LAUNCHER"] == "isaac-sim.newton.sh"


def test_newton_selected_by_env(full_install):
    rc, out, _ = _resolve(full_install, env={"ISAACSIM_ENGINE": "newton"})
    assert rc == 0
    assert out["LAUNCHER"] == "isaac-sim.newton.sh"


def test_flag_overrides_env(full_install):
    """An explicit flag wins over the environment, not the other way around."""
    rc, out, _ = _resolve(full_install, "--physx", env={"ISAACSIM_ENGINE": "newton"})
    assert rc == 0
    assert out["LAUNCHER"] == "isaac-sim.sh"


def test_kit_arguments_are_forwarded_unchanged(full_install):
    """Engine flags are consumed; everything else reaches Kit in order."""
    rc, out, _ = _resolve(full_install, "--newton", "--/app/window/hideUi=true", "--reset-user", "extra")
    assert rc == 0
    assert out["ENGINE"] == "newton"
    assert out["ARGS"] == "--/app/window/hideUi=true --reset-user extra"


def test_unknown_engine_is_rejected(full_install):
    rc, _, err = _resolve(full_install, "--engine", "warp")
    assert rc == 1
    assert "unknown physics engine 'warp'" in err
    # The message must list what the user can actually pick.
    assert "physx" in err and "newton" in err


def test_newton_on_a_5_1_install_explains_the_version_requirement(tmp_path):
    """5.1.0 ships no Newton launcher — say why instead of a bare missing-file error."""
    root = _fake_install(tmp_path, ["isaac-sim.sh"])
    rc, _, err = _resolve(root, "--newton")
    assert rc == 1
    assert "isaac-sim.newton.sh" in err
    assert "6.0" in err


def test_missing_install_root_is_rejected(tmp_path):
    rc, _, err = _resolve(str(tmp_path / "nonexistent"))
    assert rc == 1
    assert "ISAACSIM_ROOT" in err


def test_live_view_flag_becomes_kit_exec(full_install):
    """--live-view is consumed and turned into `--exec scripts/live_view.py` for Kit."""
    live_view = os.path.join(REPO_ROOT, "scripts", "live_view.py")
    rc, out, _ = _resolve(full_install, "--live-view", "--no-window")
    assert rc == 0
    assert out["ENGINE"] == "physx"
    assert out["ARGS"] == f"--no-window --exec {live_view}"


def test_live_view_selected_by_env(full_install):
    live_view = os.path.join(REPO_ROOT, "scripts", "live_view.py")
    rc, out, _ = _resolve(full_install, "--newton", env={"ISAAC_LIVE_VIEW": "1"})
    assert rc == 0
    assert out["LAUNCHER"] == "isaac-sim.newton.sh"
    assert out["ARGS"] == f"--exec {live_view}"


def test_live_view_script_exists():
    assert os.path.isfile(os.path.join(REPO_ROOT, "scripts", "live_view.py"))
