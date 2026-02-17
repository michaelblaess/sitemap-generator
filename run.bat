@echo off
cd /d "%~dp0"
if not exist ".venv" (
    echo Bitte zuerst setup-dev-environment.bat ausfuehren!
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m sitemap_generator %*
