#!/bin/sh
set -e

# Replit-friendly bootstrap:
# - ensure pip exists
# - install lightweight backend deps (FastAPI + scrapers + OpenAI-compatible client)
# - run the app on $PORT

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Error: Python is not installed (python/python3 not found)." >&2
  exit 127
fi

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r backend/requirements-light.txt

exec ./start.sh
