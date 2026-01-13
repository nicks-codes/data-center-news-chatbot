#!/bin/sh
# Start script for Railway/Render/Replit deployment
set -e

PORT="${PORT:-8000}"

# Prefer `python` but fall back to `python3` (common on Linux)
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Error: Python is not installed (python/python3 not found)." >&2
  exit 127
fi

exec "$PYTHON_BIN" -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
