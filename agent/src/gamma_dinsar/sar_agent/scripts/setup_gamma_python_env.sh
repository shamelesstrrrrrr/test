#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS_FILE="${SCRIPT_DIR}/gamma_python_requirements.txt"
PYTHON_BIN="${PYTHON_BIN:-python}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Cannot find Python interpreter: ${PYTHON_BIN}" >&2
  exit 1
fi

echo "Installing GAMMA TOPS coregistration Python dependencies with: ${PYTHON_BIN}"
"${PYTHON_BIN}" -m pip install --upgrade -r "${REQUIREMENTS_FILE}"

"${PYTHON_BIN}" - <<'PYTHON_CHECK'
import sys
import distutils
import matplotlib
import numpy
from scipy.constants import speed_of_light

print(f"Python: {sys.executable}")
print(f"Python version: {sys.version.split()[0]}")
print(f"NumPy: {numpy.__version__}")
print(f"Matplotlib: {matplotlib.__version__}")
print(f"Speed of light: {speed_of_light}")
print("GAMMA TOPS coregistration Python environment is ready.")
PYTHON_CHECK
