#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "[ERROR] Python 3.10+ not found. Install it from https://www.python.org/downloads/ or your package manager." >&2
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
  echo "[ERROR] Python 3.10 or newer is required. Found: $($PY --version)" >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "Creating virtual environment..."
  "$PY" -m venv .venv || { echo "[ERROR] venv creation failed. On Debian/Ubuntu run: sudo apt install python3-venv" >&2; exit 1; }
fi
echo "Installing dependencies (first run needs internet)..."
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt || { echo "[ERROR] Dependency installation failed. Check your internet connection." >&2; exit 1; }
echo "Starting Storm Watch at http://localhost:8501  (Ctrl+C to stop)"
exec .venv/bin/python -m streamlit run app.py
