#!/usr/bin/env bash

set -euo pipefail

echo "=== Yad2 Scraper Runner (macOS / Linux) ==="

if [ ! -x ".venv/bin/python" ]; then
  echo "Virtual environment not found or Python is not executable at .venv/bin/python."
  echo "Please run ./setup_yad2_scraper_macos.sh first, then re-run this script."
  exit 1
fi

OUTPUT_DIR="$(pwd)/output"

echo "Using virtualenv Python:"
.venv/bin/python --version || true
echo "Output directory: ${OUTPUT_DIR}"
echo

.venv/bin/python yad2_pipeline.py \
  --output-dir "${OUTPUT_DIR}" \
  --max-pages 2 \
  --captcha-avoidance-min 0 \
  --headless 0 \
  --areas "Ramat HaSharon & Herzliya Area,Rishon LeZion Area, Netanya Area"

echo
echo "=== Scraper finished ==="
echo "Results are in: ${OUTPUT_DIR}"

