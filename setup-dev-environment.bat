@echo off
echo === Playwright Sitemap Generator - Dev Setup ===
cd /d "%~dp0"

echo.
echo [1/4] Erstelle Virtual Environment...
python -m venv .venv

echo [2/4] Installiere Abhaengigkeiten...
.venv\Scripts\pip.exe install -e .

echo [3/4] Installiere Playwright Chromium...
.venv\Scripts\playwright.exe install chromium

echo [4/4] Fertig!
echo.
echo Starten mit: run.bat https://example.com
pause
