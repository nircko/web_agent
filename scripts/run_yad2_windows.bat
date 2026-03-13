@echo off
REM ============================================
REM  Yad2 Scraper - Windows Runner Launcher
REM ============================================

REM Change to the project root (parent of this scripts folder)
cd /d "%~dp0\.."

echo ============================================
echo  Running Yad2 scraper (Windows)...
echo  Make sure you ran:
echo    scripts\setup_yad2_scraper_windows.bat
echo  at least once on this machine.
echo ============================================
echo.

powershell -ExecutionPolicy Bypass -File ".\scripts\run_yad2_windows.ps1"

echo.
echo ============================================
echo  Scraper finished. Check the 'output' folder
echo  in this directory for results.
echo ============================================
echo.
pause

