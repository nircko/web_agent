#!/bin/bash
# Double-click launcher for the Listing Inspector web UI (macOS).
#
# Usage:
#   1. Make executable once:
#        chmod +x scripts/launch_web_ui_macos.command
#   2. Then just double-click this file in Finder.
#
# It will open a Terminal window, start the web UI, and print the URL:
#   http://127.0.0.1:8000/

cd "$(dirname "$0")/.."

echo "Starting Listing Inspector web UI..."
echo "Project directory: $(pwd)"
echo

python3 -m uvicorn web_ui.api:app --host 127.0.0.1 --port 8000

echo
echo "Web UI stopped. You can close this window."

