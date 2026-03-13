<# 
 Core runner script used by the Windows .bat launcher.
#>

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Yad2 Scraper Runner (Windows) ===" -ForegroundColor Cyan

$venvPython = ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found at $venvPython." -ForegroundColor Red
    Write-Host "Please run setup_yad2_scraper_windows.bat first, then re-run this script." -ForegroundColor Yellow
    exit 1
}

$OUTPUT_DIR = Join-Path (Get-Location) "output"

Write-Host ("Using virtualenv Python: {0}" -f $venvPython) -ForegroundColor Green
& $venvPython --version
Write-Host ("Output directory: {0}" -f $OUTPUT_DIR) -ForegroundColor Green
Write-Host "" 

& $venvPython yad2_pipeline.py `
  --output-dir "$OUTPUT_DIR" `
  --max-pages 2 `
  --captcha-avoidance-min 0 `
  --headless 1 `
  --areas "Rishon LeZion Area, Netanya Area"

Write-Host ""
Write-Host "=== Scraper finished ===" -ForegroundColor Cyan
Write-Host ("Results are in: {0}" -f $OUTPUT_DIR) -ForegroundColor Green

