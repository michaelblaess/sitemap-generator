#!/usr/bin/env bash
# bootstrap.sh - sets up the sitemap-generator development environment.
#
# Creates the .venv via uv, installs runtime + dev dependencies, the Nuitka
# build tool (for compile-linux.sh / compile-macos.sh) and the Playwright
# Chromium browser. Run once after cloning the repo.

set -euo pipefail
cd "$(dirname "$0")"

echo "=== sitemap-generator - dev environment ==="

echo "[1/3] venv + dependencies (uv sync)..."
uv sync --extra dev

echo "[2/3] Nuitka build tool..."
uv pip install nuitka

echo "[3/3] Playwright Chromium..."
uv run playwright install chromium

echo ""
echo "Done. Start with: ./run.sh https://example.com"
