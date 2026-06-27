#!/usr/bin/env bash
# Install local sibling-repo dependencies.
#
# Why this script exists:
#   - AgentScope: NOT a pip package. We depend on the sibling repo at
#     `../AgentScope` (relative to this backend/) and install it editable
#     so any edit there is picked up on next import.
#
# Usage (from repo root or backend/):
#     bash backend/scripts/install_local_deps.sh

set -euo pipefail

# Resolve the backend dir (where this script lives) and its parent.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"

AGENTSCOPE_DIR="${REPO_ROOT}/AgentScope"

echo "[install_local_deps] repo root:       ${REPO_ROOT}"
echo "[install_local_deps] agentscope dir:  ${AGENTSCOPE_DIR}"

# Sanity checks
if [ ! -d "${AGENTSCOPE_DIR}" ] || [ ! -f "${AGENTSCOPE_DIR}/pyproject.toml" ]; then
  echo "ERROR: AgentScope repo not found at ${AGENTSCOPE_DIR}" >&2
  exit 1
fi

# Install AgentScope in editable mode
echo "[install_local_deps] Installing AgentScope (editable) ..."
python -m pip install -e "${AGENTSCOPE_DIR}"

# Verify imports
echo "[install_local_deps] Verifying imports ..."
python - <<'PY'
# AgentScope
from agentscope.agent import Agent  # noqa: F401
from agentscope import logger  # noqa: F401
print("[install_local_deps] agentscope.Agent OK")
PY

echo "[install_local_deps] Done."
