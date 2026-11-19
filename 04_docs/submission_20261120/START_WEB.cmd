@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 run_web.py
) else (
  python run_web.py
)
if errorlevel 1 (
  echo Python 3.11 or newer is required. See README.md.
  pause
)
