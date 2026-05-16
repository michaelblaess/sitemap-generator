#Requires -Version 5.1
# run.ps1 - starts sitemap-generator from source.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Please run .\bootstrap.ps1 first." -ForegroundColor Red
    exit 1
}

& ".venv\Scripts\python.exe" -m sitemap_generator @args
