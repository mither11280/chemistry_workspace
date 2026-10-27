#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
if [[ -n "${PYTHON_BIN:-}" ]]; then
  BUILD_PYTHON="$PYTHON_BIN"
elif [[ -x .packaging-venv/bin/python ]]; then
  BUILD_PYTHON="$PWD/.packaging-venv/bin/python"
else
  BUILD_PYTHON="$(command -v python3)"
fi
exec "$BUILD_PYTHON" scripts/build_macos.py "$@"
