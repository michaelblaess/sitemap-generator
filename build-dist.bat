@echo off
echo === Sitemap Generator - Build ===
cd /d "%~dp0"

if not exist ".venv" (
    echo Bitte zuerst setup-dev-environment.bat ausfuehren!
    pause
    exit /b 1
)

echo.
echo [1/3] Installiere PyInstaller...
.venv\Scripts\pip.exe install pyinstaller

echo [2/3] Erstelle Executable...
.venv\Scripts\pyinstaller.exe ^
    --name sitemap-generator ^
    --onedir ^
    --console ^
    --add-data "src\sitemap_generator\app.tcss;sitemap_generator" ^
    --hidden-import sitemap_generator ^
    --hidden-import sitemap_generator.app ^
    --hidden-import sitemap_generator.models ^
    --hidden-import sitemap_generator.models.crawl_result ^
    --hidden-import sitemap_generator.models.robots ^
    --hidden-import sitemap_generator.models.sitemap_writer ^
    --hidden-import sitemap_generator.models.settings ^
    --hidden-import sitemap_generator.services ^
    --hidden-import sitemap_generator.services.crawler ^
    --hidden-import sitemap_generator.widgets ^
    --hidden-import sitemap_generator.widgets.url_table ^
    --hidden-import sitemap_generator.widgets.stats_panel ^
    --hidden-import sitemap_generator.widgets.summary_panel ^
    --hidden-import sitemap_generator.screens ^
    --hidden-import sitemap_generator.screens.about ^
    --collect-submodules rich._unicode_data ^
    src\sitemap_generator\__main__.py

echo [3/3] Fertig!
echo.
echo Executable in: dist\sitemap-generator\
pause
