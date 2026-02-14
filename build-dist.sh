#!/usr/bin/env bash
set -e
echo "=== Playwright Sitemap Generator - Build ==="
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Bitte zuerst setup-dev-environment.sh ausfuehren!"
    exit 1
fi

echo ""
echo "[1/3] Installiere PyInstaller..."
.venv/bin/pip install pyinstaller

echo "[2/3] Erstelle Executable..."
.venv/bin/pyinstaller \
    --name playwright-sitemap-generator \
    --onedir \
    --console \
    --add-data "src/playwright_sitemap_generator/app.tcss:playwright_sitemap_generator" \
    --hidden-import playwright_sitemap_generator \
    --hidden-import playwright_sitemap_generator.app \
    --hidden-import playwright_sitemap_generator.models \
    --hidden-import playwright_sitemap_generator.models.crawl_result \
    --hidden-import playwright_sitemap_generator.models.robots \
    --hidden-import playwright_sitemap_generator.models.sitemap_writer \
    --hidden-import playwright_sitemap_generator.models.settings \
    --hidden-import playwright_sitemap_generator.services \
    --hidden-import playwright_sitemap_generator.services.crawler \
    --hidden-import playwright_sitemap_generator.widgets \
    --hidden-import playwright_sitemap_generator.widgets.url_table \
    --hidden-import playwright_sitemap_generator.widgets.stats_panel \
    --hidden-import playwright_sitemap_generator.widgets.summary_panel \
    --hidden-import playwright_sitemap_generator.screens \
    --hidden-import playwright_sitemap_generator.screens.about \
    src/playwright_sitemap_generator/__main__.py

echo "[3/3] Fertig!"
echo ""
echo "Executable in: dist/playwright-sitemap-generator/"
