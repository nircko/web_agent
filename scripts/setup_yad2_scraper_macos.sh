#!/usr/bin/env bash

set -euo pipefail

echo "=== Yad2 Scraper Setup (macOS / Linux) ==="

# 1. Prefer using the Python 3.12 version from an existing .venv, if present.
if [ -x ".venv/bin/python" ]; then
  echo "Existing virtual environment detected. Using its Python version:"
  .venv/bin/python --version || true
else
  # Ensure Python 3.12 is installed (try to auto-install via Homebrew when possible)
  if ! command -v python3.12 >/dev/null 2>&1; then
    echo "Python 3.12 was not found on your PATH."
    if command -v brew >/dev/null 2>&1; then
      echo "Homebrew detected. Installing Python 3.12 via Homebrew ..."
      brew install python@3.12 || {
        echo "Homebrew failed to install Python 3.12. Please install Python 3.12 manually from https://www.python.org/downloads/ and re-run this script."
        exit 1
      }
    else
      echo "Homebrew is not installed. Please either:"
      echo "  - Install Homebrew from https://brew.sh/ and then run: brew install python@3.12"
      echo "  - Or install Python 3.12 directly from https://www.python.org/downloads/"
      exit 1
    fi
  fi

  echo "Using system Python 3.12 to create virtual environment: $(command -v python3.12)"

  # 2. Create virtual environment with Python 3.12
  if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv with python3.12 ..."
    python3.12 -m venv .venv
  else
    echo "Virtual environment .venv already exists, reusing it."
  fi
fi

echo "Activating virtual environment ..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Upgrading pip ..."
python -m pip install --upgrade pip

# 3. Install Python dependencies
if [ ! -f "requirements.txt" ]; then
  echo "requirements.txt not found in the current folder."
  echo "Make sure you run this script from the project root (where requirements.txt is)."
  exit 1
fi

echo "Installing Python packages from requirements.txt ..."
pip install -r requirements.txt

# 4. Install Playwright browsers
echo "Installing Playwright browsers (Chromium, etc.) ..."
python -m playwright install

# 5. Create or update .env with required keys
ENV_FILE=".env"
echo
echo "Now we will configure API keys used for geocoding and routing."

read -r -p "Enter your OpenRouteService API key (ORS_API_KEY), or leave empty to skip routing: " ORS_API_KEY
read -r -p "Enter your email for Nominatim (GEOCODING_EMAIL), used only in headers (recommended): " GEOCODING_EMAIL

{
  echo "ORS_API_KEY=${ORS_API_KEY}"
  echo "GEOCODING_EMAIL=${GEOCODING_EMAIL:-example@example.com}"
} > "${ENV_FILE}"

echo
echo "Wrote configuration to ${ENV_FILE}:"
cat "${ENV_FILE}"

echo
echo "=== Setup complete ==="

