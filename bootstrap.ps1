#Requires -Version 5.1
<#
.SYNOPSIS
    Sets up the sitemap-generator development environment.

.DESCRIPTION
    Creates the .venv via uv, installs runtime + dev dependencies, the Nuitka
    build tool (for compile-win64.ps1) and the Playwright Chromium browser.
    Run once after cloning the repo.
#>

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== sitemap-generator - dev environment ===" -ForegroundColor Cyan

Write-Host "[1/3] venv + dependencies (uv sync)..."
uv sync --extra dev
if ($LASTEXITCODE -ne 0) { throw "uv sync fehlgeschlagen" }

Write-Host "[2/3] Nuitka build tool..."
uv pip install nuitka
if ($LASTEXITCODE -ne 0) { throw "nuitka-Installation fehlgeschlagen" }

Write-Host "[3/3] Playwright Chromium..."
uv run playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "playwright install fehlgeschlagen" }

Write-Host ""
Write-Host "Done. Start with: .\run.ps1 https://example.com" -ForegroundColor Green
