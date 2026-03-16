#!/usr/bin/env bash

# Build a macOS app bundle for the Listing Inspector web UI using PyInstaller.
#
# Usage (from project root):
#   chmod +x packaging/build_web_ui_macos.sh
#   ./packaging/build_web_ui_macos.sh
#
# After it completes, you will have something like:
#   dist/LaunchListingInspector
# (a standalone binary you can double-click in Finder).

set -euo pipefail

PYTHON="${PYTHON:-python3}"
APP_NAME="${APP_NAME:-LaunchListingInspector}"

echo "=== Building Listing Inspector app (macOS) ==="

# Ensure we are in the project root (script lives in packaging/)
cd "$(dirname "$0")/.."
echo "Project root: $(pwd)"

echo "Checking for pyinstaller..."
if ! "$PYTHON" -m pip show pyinstaller >/dev/null 2>&1; then
  echo "pyinstaller not found; installing..."
  "$PYTHON" -m pip install pyinstaller
fi

ENTRY="launch_web_ui.py"
if [ ! -f "$ENTRY" ]; then
  echo "ERROR: Entry file $ENTRY not found. Run this from the repo root."
  exit 1
fi

echo "Running PyInstaller..."
"$PYTHON" -m PyInstaller \
  --onefile \
  --windowed \
  --name "$APP_NAME" \
  --add-data "assets:assets" \
  --hidden-import "web_ui.api" \
  --hidden-import "uvicorn" \
  "$ENTRY"

echo
echo "Build complete."
echo "You can find the app/binary under: dist/$APP_NAME"
echo "Copy it together with the 'assets' folder and preference JSON files to your target Mac."
echo

