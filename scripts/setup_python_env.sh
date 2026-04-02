#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_SPEC="${PYTHON_SPEC:-/usr/bin/python3.10}"

cd "$REPO_ROOT"

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment with: $PYTHON_SPEC"
  uv venv --python "$PYTHON_SPEC"
else
  echo "Using existing virtual environment at: $REPO_ROOT/.venv"
fi

echo "Installing isaacsim-mcp-server and dependencies"
uv pip install --python .venv/bin/python -e "."

echo
echo "Done."
echo "Activate with: source .venv/bin/activate"
