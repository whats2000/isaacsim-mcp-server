# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                              # install deps (creates .venv)
uv run pre-commit install            # ruff lint+format on commit
uv run pytest                        # unit suite only; live tests skip unless opted in
ISAAC_MCP_LIVE_TESTS=1 uv run pytest # ALSO runs tests that MUTATE a running Isaac Sim
uv run pytest tests/test_adapter_v6.py::test_get_adapter_returns_v6_when_version_6   # single test
uv run ruff check . && uv run ruff format .                                 # what CI enforces
uv run python add_license_headers.py # prepend the MIT header to new .py files
```

Live testing (unit tests alone are **not** sufficient — CONTRIBUTING requires verifying in a running simulator, and stating the Isaac Sim version in the PR):

```bash
./scripts/run_isaac_sim.sh              # Kit + extension; --newton / --physx / ISAACSIM_ENGINE
./scripts/dev_mcp_server.sh             # MCP server + extension hot-reload watcher
python scripts/smoke_test.py            # one socket command per surface, pass/fail per check
python scripts/smoke_test.py --port 8767   # a second instance (e.g. 5.1 alongside 6.0)
./.venv/bin/python -m mcp dev ./isaac_mcp/server.py   # MCP inspector on :5173
```

`dev_mcp_server.sh` reloads handler/adapter modules inside the running Kit process, so extension edits do not need an Isaac Sim restart. MCP-server-side edits (`isaac_mcp/`) do need the MCP client to restart the server.

## Architecture

Two processes, one JSON-over-TCP hop (localhost:8766, `ISAAC_MCP_PORT` to change):

```
MCP client → isaac_mcp/ (FastMCP, stdio) → socket → isaac.sim.mcp_extension/ (Omniverse ext) → adapter → Isaac Sim APIs
```

**MCP side** — [isaac_mcp/server.py](isaac_mcp/server.py) builds `FastMCP`, attaches the `_INSTRUCTIONS` block (the agent-facing contract doc: workflow, debug loop, silent-failure map), and calls `register_all_tools`. Each module in [isaac_mcp/tools/](isaac_mcp/tools/) exposes `register_tools(mcp, get_connection)`; every tool serializes params, calls `conn.send_command("<category>.<verb>", params)`, and returns `json.dumps(result)`. Tools never raise — errors come back as `{"status": "error", "message": ...}` JSON strings.

[isaac_mcp/connection.py](isaac_mcp/connection.py) holds a singleton socket. It probes with `MSG_PEEK` before each send because the MCP server outlives Kit restarts; a stale socket is redialled rather than retried after failure (replaying a `create_robot`/`delete` would be worse than the error).

**Extension side** — [extension.py](isaac.sim.mcp_extension/isaac_sim_mcp_extension/extension.py) picks an adapter, fills a `Dict[str, handler]` registry, and starts [socket_server.py](isaac.sim.mcp_extension/isaac_sim_mcp_extension/socket_server.py). Command strings are the wire contract (`"lighting.create"`, `"simulation.step"`, …) and must match on both sides. A handler returning anything other than `{"status": "success", ...}` is converted into an error response by `_execute_command`.

**Adapters** — [adapters/base.py](isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/base.py) is the ABC plus the shared physics helpers; [v5.py](isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v5.py) targets Isaac Sim 5.1 (`isaacsim.core.api/.prims/.utils`), [v6.py](isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters/v6.py) targets 6.0 PhysX **and** Newton (`isaacsim.core.experimental.*`, `SimulationManager`, `isaacsim.sensors.experimental.rtx`). `get_adapter()` reads `isaacsim.core.version.get_version()` — a string on 5.x, a tuple on 6.0 — and falls back to V5 on detection failure. Handlers must stay version-agnostic: anything version-specific belongs behind an abstract method.

### Adding a tool

Five places, in order: `isaac_mcp/tools/<category>.py` → new command string → `handlers/<category>.py` `register()` → abstract method in `adapters/base.py` implemented in **both** `v5.py` and `v6.py` → if you add a new *module*, add it to the reload lists in `scripts/dev_mcp_server.sh` and to both `__init__.py` module lists. A module the reload list misses is worse than no hot reload at all: `v5`/`v6` bind imported names at module scope, so edits to it stay invisible while everything around it updates, and a live measurement then runs against stale code. `adapters/units.py` and `adapters/transforms.py` were missed exactly this way. `extension.toml` dependencies gate what the extension can import on each version — V6-only extensions must be `{ optional = true }` or 5.1 fails to load.

## Conventions and traps

- Every `.py` file carries the MIT header block; `add_license_headers.py` applies it.
- Handlers **must not** call `omni.kit.app.update()` — they run as an asyncio task on Kit's main loop and pumping it crashes Kit (see the comment in `socket_server._dispatch_command`). `v6.step` uses `SimulationManager.step` under PhysX and `NewtonStage.step_sim` under Newton, both of which advance physics without an app frame; the Newton pump survives only as a fallback for builds without `step_sim`.
- Several tests assert on *source substrings* of tool docstrings and the server instruction block ([tests/test_tool_docstrings.py](tests/test_tool_docstrings.py)) — rewording docs breaks tests, deliberately. Update both together.
- [tests/conftest.py](tests/conftest.py) stubs `carb`, `omni`, `pxr`, and `numpy` into `sys.modules` so the extension imports outside Kit. New runtime imports at module scope may need a stub added there; `pytest.ini_options.pythonpath` points at `isaac.sim.mcp_extension`.
- Behavioral contracts encoded in `base.py` and worth preserving — each fixed a silent-wrong-answer bug: exactly one `PhysicsScene` on the stage (a second one zeroes every velocity read), gravity written as USD direction+magnitude, Action Graphs suspended during `step` (else a ScriptNode overwrites stepped joint targets), `_ensure_physics_world` no-ops until a PhysicsScene exists.
- Debug loop is **step-only on a frozen timeline**; `play` is for the final Action-Graph run. The two modes do not mix — that split is repeated in the server instructions, tool docstrings, and adapter comments.
- ScriptNode scripts must define `setup(db)`/`compute(db)`; legacy mode (no `compute`) breaks exec scoping. Full rules in [isaac.sim.mcp_extension/.cursorrules](isaac.sim.mcp_extension/.cursorrules); working example in [demo/franka_pick_place.py](demo/franka_pick_place.py).
- Design docs and plans for past feature work live in [docs/superpowers/](docs/superpowers/).

## Cutting a release

Pushing an annotated tag `vX.Y.Z` triggers [.github/workflows/release.yml](.github/workflows/release.yml): lint + unit tests, build the wheel, publish to PyPI, then stamp the tag version into `server.json` on the runner and publish to the MCP Registry. **The tag is the source of the published version** — a release is not cut without the live sweep CONTRIBUTING requires, and the tag message states what was verified live and on which Isaac Sim runtime(s).

Before tagging, bump these by hand:

- **`isaac_mcp/__init__.py`** (`__version__`) — the PyPI wheel version. `pyproject.toml` is `dynamic = ["version"]` and reads it.
- **`CHANGELOG.md`** — cut `[Unreleased]` into `[X.Y.Z] - <date>`.
- **`isaac.sim.mcp_extension/config/extension.toml`** (`version`) — when the extension itself changed this cycle. It is a separate artifact (not on PyPI) and has historically lagged the package; keep it in step when the shipped extension differs.

**After the release publishes, bump `server.json` in the repo** (`.version` **and** `.packages[0].version`) to the just-released version and commit — required, not cosmetic. The MCP Registry is only one consumer, and `release.yml` stamps *its* copy from the tag; but other MCP clients and catalogs discover this server by reading `server.json` **directly from the repository**, so a stale committed file hands them the wrong version even while the registry entry is correct. Do it *after* the deploy (not before the tag) so the committed manifest never names a version that is not yet on PyPI — but do not skip it.

Leave these alone — nothing to change:

- **`pyproject.toml`** — dynamic version, reads `__init__.py`.
- **`uv.lock`** — the editable root package carries no pinned `version` line.

## GitHub templates are mandatory

**Every issue and every PR is written by filling in the repo's template, not by composing a document that resembles it.** Build the body *from* the template file — [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md), [.github/ISSUE_TEMPLATE/bug-report.yml](.github/ISSUE_TEMPLATE/bug-report.yml), [.github/ISSUE_TEMPLATE/feature-request.yml](.github/ISSUE_TEMPLATE/feature-request.yml) — then fill it in:

- **Every heading and every checkbox line stays byte-identical.** Tick a box (`- [ ]` → `- [x]`) and append your answer *after* the label; never reword, shorten or drop the label. `Other (please specify):` does not become `Other`, and `(unit tests alone are not sufficient)` does not get trimmed.
- **No section is dropped**, including ones that look like boilerplate. `## Who can review?` is part of the template.
- **Strip the `<!-- -->` guidance comments**; keep everything else.
- Extra sections *after* the template's own are fine — measurements, controls, reviewer notes.

Then **verify before posting**: diff the composed body against the template and confirm every non-comment line is present verbatim. Writing the body freehand and eyeballing it has failed twice; the template is the source, and the check is mechanical.

The runtime checkboxes are a claim about what you ran. Tick only what you actually ran and say which you did not — the template says stating a gap is fine and implying coverage you do not have is not, and that is the rule, not a suggestion.

## Changelog and issues

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/): `Added` / `Changed` / `Fixed`, newest version first, and a dated heading when the version is cut.

**Classify against the baseline, which is the last *released* version — not against the working tree.** An entry belongs under `Fixed` only if a user of that release could actually hit it. Anything introduced *and* resolved inside the current cycle never shipped, so it is part of the `Added`/`Changed` entry for the work that introduced it, never a fix of its own. Isaac Sim 6.0 and the Newton backend both landed in 0.6.0, so the Newton defects found while building them fold into the "Newton engine parity" bullet — a 0.5.2 user never had them. The same goes for a fix that took three passes to land: one entry, not three.

Keep each entry to a line or two — what broke, and what the user saw. Investigation notes, measurements and rejected hypotheses belong in the commit message, and in a code comment wherever they stop someone re-breaking it. A changelog that records everything is unreadable.

**Known issues do not go in the changelog.** File them on GitHub using [.github/ISSUE_TEMPLATE/bug-report.yml](.github/ISSUE_TEMPLATE/bug-report.yml) — fill in every field, and include the measurements plus any workaround. When one is later addressed, say so on the issue and close it, including issues we opened ourselves, so the record does not drift. Only a standing environment constraint (for example: one Isaac Sim instance per GPU) stays in the changelog, under `Notes`.

**Never open an issue from a single observation.** Reproduce it deliberately, more than once **and on more than one runtime**, before filing. A simulator is not a deterministic machine: an instance can crash, a GPU context can be lost, a render frame can drop, a sensor can return nothing on a frame that should have filled — and any of those looks exactly like a bug the first time you meet it. One sighting is a lead, not a finding.

The second runtime is not a formality, it is the control. A fault that appears on 5.1 and 6.0 PhysX and 6.0 Newton is in this code; a fault that appears on one and not the others is either version-specific — which is itself the finding, and belongs in the issue — or it was never a fault at all. Most false reports die at this step, so take it before writing anything up.

**Suspect your own test process first.** Every retraction in this repository's history came from the harness, not the product: a unit suite run against a live socket, a diagnostic script leaking sensor objects onto a prim that was later deleted, a stage left dirty by a previous attempt. Before filing, ask what *you* did to that instance, and re-run the case on a cold boot that does nothing else. If it survives that, it is real.

Retry it. Then decide which of these you have, and say which in the issue:

- **Reproduces every time** — file it with the exact steps and the measurements. This is the normal case and the only one that needs no caveat.
- **Reproduces sometimes** — file it, and give the count: how many attempts, how many reproduced, and what you varied between them. "1 fill in ~15 reads across two cold boots" is a finding; "it's flaky" is not.
- **Did not reproduce** — the fault may still be real, and "not reliably reproducible" is a legitimate thing to report, but *only once repeated attempts have established it*. Say how many you ran and what you changed each time. Without that, do not file: you are reporting a crash you saw once, and it belongs in the working notes until someone can trigger it.

The number of attempts is itself evidence and belongs in the issue body. An issue that cannot say how many times anyone tried to reproduce it wastes the next reader's time, and each Isaac Sim boot is minutes — do not spend that budget on a lead you did not chase yourself first.

**Closing an issue takes the same evidence as opening one.** A patch is not a fix until it has been confirmed live, several times, on **every version the bug was reproduced on** — 5.1, 6.0 PhysX and 6.0 Newton as applicable. One green read after a change proves the code path ran once, not that the defect is gone; sensors and physics both produce right answers intermittently, which is how a half-fix passes a single check.

Confirm on each affected runtime, more than once per runtime, then close the issue with the measurements from each. Do not close on a fix verified in one version and assumed in another, even when the versions share the adapter — if it was measured broken on Newton, it is closed on Newton. If a runtime cannot be checked (`isaac_mcp/` changes need an MCP client restart, which Kit's extension reload does not cover), say so on the issue and name what was substituted instead, rather than implying coverage you do not have.

Unit tests are necessary and never sufficient here: the whole reason this project keeps a live sweep is that the fakes standing in for a stage, a physics step or an OmniGraph are exactly the assumptions that break.
