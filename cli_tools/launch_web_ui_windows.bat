@echo off
REM ============================================
REM  Listing Inspector Web UI - Windows launcher
REM ============================================
REM
REM Usage:
REM   Double-click this file in Explorer.
REM
REM It will:
REM   - change directory to the project root
REM   - run: python -m uvicorn web_ui.api:app --host 127.0.0.1 --port 8000
REM   - show you the URL to open in your browser.

cd /d "%~dp0.."

echo.
echo ================================
echo  Starting Listing Inspector UI
echo ================================
echo.
echo Project directory: %cd%
echo.
echo If the browser does not open automatically, go to:
echo   http://127.0.0.1:8000/
echo.

python -m uvicorn web_ui.api:app --host 127.0.0.1 --port 8000

echo.
echo ================================
echo  Listing Inspector UI stopped.
echo  You can now close this window.
echo ================================
echo.
pause

