@echo off
REM ============================================
REM  Yad2 Scraper - One-click launcher (Windows)
REM ============================================

REM This script assumes the following layout:
REM   ready_for_windows\
REM     yad2_scraper.exe
REM     run_scraper.bat   (this file)
REM     assets\           (JSON mapping files)
REM     config\           (optional config)
REM     .playwright\      (Playwright browser binaries, e.g. Chromium)
REM     .env              (optional: API keys for routing/geocoding)

REM Change to the folder containing this script.
cd /d "%~dp0"

echo ================================
echo   Starting Yad2 scraper...
echo ================================
echo.

REM Ensure Playwright browsers path is set to the local .playwright folder
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright"

REM Default output folder (relative to this directory)
set "OUTPUT_DIR=%~dp0output"

REM Ask user for simple configuration (they can press Enter to accept defaults)
set "DEFAULT_MAX_PAGES=2"
set "DEFAULT_HEADLESS=1"
set "DEFAULT_AREAS=Rishon LeZion Area, Netanya Area"

echo.
set /p USER_OUTPUT_DIR=Enter output folder [default: %OUTPUT_DIR%]:
if not "%USER_OUTPUT_DIR%"=="" set "OUTPUT_DIR=%USER_OUTPUT_DIR%"

echo.
set /p USER_MAX_PAGES=Enter max pages per area [default: %DEFAULT_MAX_PAGES%]:
if "%USER_MAX_PAGES%"=="" (
  set "MAX_PAGES=%DEFAULT_MAX_PAGES%"
) else (
  set "MAX_PAGES=%USER_MAX_PAGES%"
)

echo.
set /p USER_HEADLESS=Run headless? 1=no UI, 0=show browser [default: %DEFAULT_HEADLESS%]:
if "%USER_HEADLESS%"=="" (
  set "HEADLESS=%DEFAULT_HEADLESS%"
) else (
  set "HEADLESS=%USER_HEADLESS%"
)

echo.
set /p USER_AREAS=Enter areas (comma-separated) [default: %DEFAULT_AREAS%]:
if "%USER_AREAS%"=="" (
  set "AREAS=%DEFAULT_AREAS%"
) else (
  set "AREAS=%USER_AREAS%"
)

echo.
echo Using:
echo   Output dir : %OUTPUT_DIR%
echo   Max pages  : %MAX_PAGES%
echo   Headless   : %HEADLESS%
echo   Areas      : %AREAS%
echo.

.\yad2_scraper.exe ^
  --output-dir "%OUTPUT_DIR%" ^
  --max-pages %MAX_PAGES% ^
  --captcha-avoidance-min 0 ^
  --headless %HEADLESS% ^
  --areas "%AREAS%"

echo.
echo ================================
echo   Scraper finished.
echo   CSV and logs are in: %OUTPUT_DIR%
echo ================================
echo.
pause

