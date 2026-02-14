#!/usr/bin/env bash
set -e
echo "=== Playwright Sitemap Generator - Dev Setup ==="
cd "$(dirname "$0")"

echo ""
echo "[1/4] Erstelle Virtual Environment..."
python3 -m venv .venv

echo "[2/4] Installiere Abhaengigkeiten..."
.venv/bin/pip install -e .

echo "[3/4] Installiere Playwright Chromium..."
.venv/bin/playwright install chromium

echo "[4/4] Fertig!"
echo ""
echo "Starten mit: ./run.sh https://example.com"
