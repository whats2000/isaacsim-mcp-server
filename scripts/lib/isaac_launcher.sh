#!/usr/bin/env bash
# Shared helper: pick which Isaac Sim launcher (physics engine) to run.
#
# Isaac Sim ships one launcher script per physics backend. They differ only in
# the .kit app file they exec, so selecting an engine is purely a matter of
# choosing the right launcher name.
#
# To support a new engine, add one entry to ENGINE_LAUNCHERS below. That single
# line enables `ISAACSIM_ENGINE=<name>` and `--<name>` everywhere this helper is
# sourced — no other edit anywhere.

# engine name -> launcher script shipped in the Isaac Sim install root
declare -A ENGINE_LAUNCHERS=(
  [physx]="isaac-sim.sh"
  [newton]="isaac-sim.newton.sh"
)

ISAAC_DEFAULT_ENGINE="physx"

# Browser live view (scripts/live_view.py), started inside Kit via --exec.
ISAAC_LIVE_VIEW_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/live_view.py"

# isaac_resolve_launcher <isaacsim_root> [args...]
#
# Selection order (later wins):
#   1. ISAAC_DEFAULT_ENGINE
#   2. $ISAACSIM_ENGINE
#   3. --engine <name> / --engine=<name> / --<name> on the command line
#
# --live-view (or ISAAC_LIVE_VIEW=1) is consumed here too and becomes
# `--exec scripts/live_view.py` for Kit, so every launcher gets the browser view.
#
# On success sets:
#   ISAACSIM_ENGINE        resolved engine name
#   ISAAC_SIM_SH           absolute path to the launcher to exec
#   ISAAC_PASSTHRU_ARGS    array of args to forward to it (engine flags removed)
#
# Returns 1 with a message on stderr for an unknown engine or a missing launcher.
isaac_resolve_launcher() {
  local root="$1"
  shift
  local engine="${ISAACSIM_ENGINE:-$ISAAC_DEFAULT_ENGINE}"
  local live_view="${ISAAC_LIVE_VIEW:-0}"

  ISAAC_PASSTHRU_ARGS=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --engine)
        engine="${2:-}"
        shift 2
        ;;
      --engine=*)
        engine="${1#*=}"
        shift
        ;;
      --live-view)
        live_view=1
        shift
        ;;
      --*)
        # --physx / --newton / --<any registered engine> are engine selectors;
        # every other flag belongs to Kit and is forwarded untouched.
        local candidate="${1#--}"
        if [[ -n "${ENGINE_LAUNCHERS[$candidate]:-}" ]]; then
          engine="$candidate"
        else
          ISAAC_PASSTHRU_ARGS+=("$1")
        fi
        shift
        ;;
      *)
        ISAAC_PASSTHRU_ARGS+=("$1")
        shift
        ;;
    esac
  done

  if [[ -z "${ENGINE_LAUNCHERS[$engine]:-}" ]]; then
    echo "Error: unknown physics engine '$engine'." >&2
    echo "Known engines: ${!ENGINE_LAUNCHERS[*]}" >&2
    return 1
  fi

  if [[ "$live_view" == "1" ]]; then
    ISAAC_PASSTHRU_ARGS+=(--exec "$ISAAC_LIVE_VIEW_SCRIPT")
  fi

  ISAACSIM_ENGINE="$engine"
  ISAAC_SIM_SH="$root/${ENGINE_LAUNCHERS[$engine]}"

  if [[ ! -x "$ISAAC_SIM_SH" ]]; then
    echo "Error: launcher for engine '$engine' not found at: $ISAAC_SIM_SH" >&2
    if [[ "$engine" != "physx" ]]; then
      echo "The '$engine' engine ships with Isaac Sim 6.0 and later; this install may be older." >&2
    fi
    echo "Set ISAACSIM_ROOT to your Isaac Sim install directory and try again." >&2
    return 1
  fi

  return 0
}
