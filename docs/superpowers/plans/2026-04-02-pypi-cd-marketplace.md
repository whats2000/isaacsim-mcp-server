# PyPI & CD Marketplace Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `isaac-sim-mcp` to PyPI with a tag-triggered CD pipeline and register on MCP marketplaces (Smithery, mcp.run).

**Architecture:** A `pyproject.toml` makes the `isaac_mcp` package installable via pip. GitHub Actions runs ruff lint/format on PRs (CI) and builds+publishes to PyPI on `v*` tags (CD). Registry manifests (`smithery.yaml`) let marketplaces discover the server.

**Tech Stack:** Python 3.10+, hatchling (build), ruff (lint/format), GitHub Actions, PyPI OIDC trusted publisher, Smithery

**Spec:** `docs/superpowers/specs/2026-04-02-pypi-cd-marketplace-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `pyproject.toml` | Create | Package metadata, build config, dependencies, entry point |
| `ruff.toml` | Create | Linter/formatter configuration |
| `.github/workflows/ci.yml` | Create | Lint + format checks on PRs |
| `.github/workflows/release.yml` | Create | Build + publish to PyPI + GitHub Release on `v*` tags |
| `smithery.yaml` | Create | Smithery registry manifest |
| `isaac_mcp/__init__.py` | Modify | Bump version to `0.4.0` |
| `README.md` | Modify | Add PyPI badge and `pip install` instructions |

---

### Task 1: Create `pyproject.toml`

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "isaac-sim-mcp"
dynamic = ["version"]
description = "Control NVIDIA Isaac Sim robotics simulator through MCP -- 39 tools for scene management, robot control, sensors, and simulation"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [
    { name = "omni-mcp" },
]
keywords = ["mcp", "isaac-sim", "robotics", "simulation", "nvidia"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Topic :: Software Development :: Libraries",
]
dependencies = [
    "mcp[cli]",
]

[project.urls]
Homepage = "https://github.com/omni-mcp/isaac-sim-mcp"
Repository = "https://github.com/omni-mcp/isaac-sim-mcp"
Issues = "https://github.com/omni-mcp/isaac-sim-mcp/issues"

[project.scripts]
isaac-sim-mcp = "isaac_mcp.server:main"

[tool.hatch.version]
path = "isaac_mcp/__init__.py"

[tool.hatch.build.targets.sdist]
include = ["isaac_mcp/"]

[tool.hatch.build.targets.wheel]
packages = ["isaac_mcp"]
```

- [ ] **Step 2: Verify the build works locally**

Run:
```bash
pip install hatch && hatch build
```
Expected: `dist/` contains `isaac_sim_mcp-0.4.0.tar.gz` and `isaac_sim_mcp-0.4.0-py3-none-any.whl` (version will be `0.1.0` until we bump in Task 3).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pyproject.toml for PyPI packaging"
```

---

### Task 2: Create `ruff.toml`

**Files:**
- Create: `ruff.toml`

- [ ] **Step 1: Create `ruff.toml`**

```toml
target-version = "py310"
line-length = 120

[lint]
select = ["E", "F", "W", "I"]
ignore = ["E501"]

[format]
quote-style = "double"
```

- [ ] **Step 2: Run ruff to verify it works**

Run:
```bash
pip install ruff && ruff check isaac_mcp/ && ruff format --check isaac_mcp/
```
Expected: ruff runs without crashing. There may be existing lint/format issues — note them but don't fix in this task.

- [ ] **Step 3: Commit**

```bash
git add ruff.toml
git commit -m "build: add ruff configuration for linting and formatting"
```

---

### Task 3: Bump version to `0.4.0`

**Files:**
- Modify: `isaac_mcp/__init__.py:29`

- [ ] **Step 1: Update version string**

In `isaac_mcp/__init__.py`, change:
```python
__version__ = "0.1.0"
```
to:
```python
__version__ = "0.4.0"
```

- [ ] **Step 2: Verify hatch reads the version**

Run:
```bash
hatch version
```
Expected: `0.4.0`

- [ ] **Step 3: Commit**

```bash
git add isaac_mcp/__init__.py
git commit -m "release: bump version to 0.4.0"
```

---

### Task 4: Fix existing lint issues

**Files:**
- Modify: files flagged by ruff (varies)

- [ ] **Step 1: Run ruff and capture issues**

Run:
```bash
ruff check isaac_mcp/ --output-format=text
```

- [ ] **Step 2: Auto-fix what ruff can fix**

Run:
```bash
ruff check isaac_mcp/ --fix && ruff format isaac_mcp/
```

- [ ] **Step 3: Verify clean**

Run:
```bash
ruff check isaac_mcp/ && ruff format --check isaac_mcp/
```
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "style: fix lint and format issues in isaac_mcp"
```

---

### Task 5: Create CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/` directory**

Run:
```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install ruff
        run: pip install ruff

      - name: Lint
        run: ruff check .

      - name: Format check
        run: ruff format --check .
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint and format checks on PRs"
```

---

### Task 6: Create CD workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write
  id-token: write

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install ruff
        run: pip install ruff

      - name: Lint
        run: ruff check .

      - name: Format check
        run: ruff format --check .

  build-and-publish:
    needs: lint
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/isaac-sim-mcp
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install build tools
        run: pip install hatch

      - name: Build package
        run: hatch build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1

  github-release:
    needs: build-and-publish
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "cd: add tag-triggered PyPI publish and GitHub Release"
```

---

### Task 7: Create Smithery manifest

**Files:**
- Create: `smithery.yaml`

- [ ] **Step 1: Create `smithery.yaml`**

```yaml
name: isaac-sim-mcp
description: Control NVIDIA Isaac Sim robotics simulator through MCP -- 39 tools for scene management, robot control, sensors, and simulation
license: MIT
homepage: https://github.com/omni-mcp/isaac-sim-mcp

install:
  pip: isaac-sim-mcp

start:
  command: isaac-sim-mcp

tags:
  - robotics
  - simulation
  - nvidia
  - isaac-sim
  - 3d
```

- [ ] **Step 2: Commit**

```bash
git add smithery.yaml
git commit -m "build: add Smithery registry manifest"
```

---

### Task 8: Update README with PyPI badge and install instructions

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add PyPI badge after the title**

At the top of `README.md`, after `# Isaac Sim MCP`, add:

```markdown
[![PyPI version](https://img.shields.io/pypi/v/isaac-sim-mcp)](https://pypi.org/project/isaac-sim-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
```

- [ ] **Step 2: Add pip install option to Quick Start**

After the existing "Clone the repo" section (before "Set up Python once"), add a new section:

```markdown
### Alternative: Install from PyPI

```bash
pip install isaac-sim-mcp
```

This installs the MCP server only. You still need Isaac Sim with the extension running (see steps 3-4 below).
```

- [ ] **Step 3: Verify README renders correctly**

Run:
```bash
python -m pip install restview && restview --long-description README.md
```
Or just visually inspect the markdown.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add PyPI badge and pip install instructions to README"
```

---

### Task 9: Configure PyPI trusted publisher

This task is manual — it cannot be automated via code. It must be done BEFORE the first tag push.

- [ ] **Step 1: Go to PyPI and create the trusted publisher**

1. Go to https://pypi.org/manage/account/publishing/
2. Add a new "pending publisher" with:
   - **PyPI project name:** `isaac-sim-mcp`
   - **Owner:** `omni-mcp`
   - **Repository:** `isaac-sim-mcp`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
3. Save

- [ ] **Step 2: Also create a GitHub environment**

1. Go to the repo's Settings > Environments
2. Create an environment called `pypi`
3. No protection rules needed (tags already gate the release)

---

### Task 10: Test the full pipeline

- [ ] **Step 1: Verify the build works end-to-end locally**

Run:
```bash
hatch build && pip install dist/isaac_sim_mcp-0.4.0-py3-none-any.whl && isaac-sim-mcp --help
```
Expected: The CLI entry point is available. It may fail to connect to Isaac Sim (expected), but it should start.

- [ ] **Step 2: Verify lint passes**

Run:
```bash
ruff check . && ruff format --check .
```
Expected: Clean.

- [ ] **Step 3: Clean up build artifacts**

Run:
```bash
rm -rf dist/ *.egg-info
pip uninstall isaac-sim-mcp -y
```

- [ ] **Step 4: Final commit (if any cleanup needed)**

```bash
git status
# If changes exist:
git add -u
git commit -m "chore: final cleanup for v0.4.0 release"
```

- [ ] **Step 5: Tag and push (only after Task 9 is complete)**

```bash
git tag v0.4.0
git push origin main --tags
```

- [ ] **Step 6: Verify the GitHub Actions workflow runs**

Go to the repo's Actions tab and confirm:
1. The `Release` workflow triggered
2. Lint passed
3. Package built
4. Published to PyPI
5. GitHub Release created with auto-generated notes
