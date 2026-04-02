# PyPI Publishing & CD Pipeline for MCP Marketplace Release

**Date:** 2026-04-02
**Status:** Approved

## Overview

Release `isaac-sim-mcp` to PyPI and multiple MCP registries (Smithery, mcp.run, Claude Code registry) with a tag-triggered CD pipeline via GitHub Actions. Static analysis CI runs on PRs.

## Constraints

- Tests require a running Isaac Sim instance -- cannot run in CI
- The Omniverse extension (`isaac.sim.mcp_extension/`) is NOT part of the PyPI package; it is installed separately inside Isaac Sim
- Versioning continues from `0.3.0` (next release: `0.4.0`)

## 1. Python Packaging (`pyproject.toml`)

- **PyPI package name:** `isaac-sim-mcp`
- **Import name:** `isaac_mcp` (unchanged)
- **Version source:** `isaac_mcp/__init__.py` (`__version__`), bumped to `0.4.0`
- **Build system:** `hatchling`
- **Runtime dependency:** `mcp[cli]`
- **Python requirement:** `>=3.10`
- **Entry point:** `isaac-sim-mcp = isaac_mcp.server:main` (CLI command)
- **Included packages:** Only `isaac_mcp/` -- the extension is excluded

## 2. CI Pipeline (PRs to `main`)

**File:** `.github/workflows/ci.yml`
**Trigger:** Pull requests to `main`
**Runner:** `ubuntu-latest`, Python 3.10

**Steps:**
1. Checkout code
2. Install Python + dependencies
3. `ruff check .` -- linting
4. `ruff format --check .` -- formatting

No tests in CI (documented limitation -- requires Isaac Sim).

## 3. CD Pipeline (Tag-Triggered Release)

**File:** `.github/workflows/release.yml`
**Trigger:** Push of tag matching `v*` (e.g., `v0.4.0`)
**Runner:** `ubuntu-latest`, Python 3.10

**Steps:**
1. Run static analysis (same lint + format checks as CI)
2. Build Python package (`sdist` + `wheel`) using `hatch build`
3. Publish to PyPI using `pypa/gh-action-pypi-publish` with OIDC trusted publisher (no API token needed)
4. Create GitHub Release from the tag with auto-generated release notes

**Secrets required:** None (OIDC trusted publisher for PyPI).

**Release workflow for maintainers:**
```bash
# 1. Bump version in isaac_mcp/__init__.py
# 2. Commit and tag
git commit -am "release: v0.4.0"
git tag v0.4.0
git push origin main --tags
# 3. GitHub Actions handles build, publish, and release creation
```

## 4. Registry Manifest Files

### Smithery (`smithery.yaml`)

Smithery reads this file from the repo. Contains:
- Server name, description, startup command
- Tags: `robotics`, `simulation`, `nvidia`, `isaac-sim`, `3d`
- Install command: `pip install isaac-sim-mcp`

### mcp.run / Emerging Registries

A `mcp-registry.json` file at the repo root (best-effort, format may evolve) with:
- Package name, version, transport type (`stdio`)
- Install instructions, supported platforms
- This file will be updated as registry specs stabilize

### Claude Code Registry

Currently documented via `claude mcp add` in the README. A formal manifest will be added when the Claude Code registry spec stabilizes.

## 5. Metadata (Shared Across Registries)

- **Name:** `isaac-sim-mcp`
- **Description:** "Control NVIDIA Isaac Sim robotics simulator through MCP -- 39 tools for scene management, robot control, sensors, and simulation"
- **Categories/tags:** `robotics`, `simulation`, `nvidia`, `isaac-sim`, `3d`
- **Homepage:** GitHub repo URL
- **License:** MIT

## 6. File Changes

### New Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package definition, build config, dependencies |
| `.github/workflows/ci.yml` | Lint on PRs |
| `.github/workflows/release.yml` | Build + publish on `v*` tags |
| `smithery.yaml` | Smithery registry manifest |
| `ruff.toml` | Ruff linter/formatter configuration |

### Modified Files

| File | Change |
|------|--------|
| `isaac_mcp/__init__.py` | Bump `__version__` to `0.4.0` |
| `README.md` | Add PyPI badge, `pip install` instructions, registry links |

Note: `.gitignore` already includes `dist/` and `*.egg-info/` — no changes needed.

### Unchanged

- `isaac.sim.mcp_extension/` -- separate Omniverse extension, not part of PyPI package
- `scripts/` -- existing dev workflow scripts remain functional
- `isaac_mcp/` structure -- already properly organized as a Python package
