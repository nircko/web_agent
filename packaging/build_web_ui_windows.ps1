Param(
    [string] $Python = "python",
    [string] $OutputExeName = "LaunchListingInspector.exe"
)

<# 
Build a single-file Windows EXE for the Listing Inspector web UI using PyInstaller.

Usage (from project root, in PowerShell):

  .\packaging\build_web_ui_windows.ps1

After it completes, you will have:

  dist\<OutputExeName>

You can copy that EXE together with:
  - assets\
  - scraper_preferences.json
  - madlan_preferences.json

to another Windows machine, and double-click the EXE to start the UI at:
  http://127.0.0.1:8000/
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Building Listing Inspector EXE (Windows) ==="

# Ensure we are in the project root (script lives in packaging/)
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

Write-Host "Project root: $PWD"

# Ensure pyinstaller is available
Write-Host "Checking for pyinstaller..."
& $Python -m pip show pyinstaller 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pyinstaller not found; installing..."
    & $Python -m pip install pyinstaller
}

$entry = "launch_web_ui.py"
if (-not (Test-Path $entry)) {
    Write-Error "Entry file $entry not found. Make sure you run this from the repo root."
}

Write-Host "Running PyInstaller..."
& $Python -m PyInstaller `
    --onefile `
    --name $OutputExeName `
    --add-data "assets;assets" `
    --hidden-import "web_ui.api" `
    --hidden-import "uvicorn" `
    $entry

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Build complete."
Write-Host "EXE location: dist\$OutputExeName"
Write-Host "Copy this EXE together with the 'assets' folder and preference JSON files to your target machine."
Write-Host ""

