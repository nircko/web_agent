@echo off
REM ============================================
REM  Yad2 Scraper - Windows Setup Launcher
REM ============================================

REM Change to the project root (folder containing this script)
cd /d "%~dp0\.."

echo ============================================
echo  Running Yad2 setup (Windows)...
echo  This will install Python (if needed), create
echo  a virtual environment, install packages, and
echo  configure Playwright and .env.
echo ============================================
echo.

powershell -ExecutionPolicy Bypass -File ".\scripts\setup_yad2_scraper_windows.ps1"

echo.
echo ============================================
echo  Setup finished. If you saw no errors above,
echo  you can now run:
echo    scripts\run_yad2_windows.bat
echo ============================================
echo.
pause

