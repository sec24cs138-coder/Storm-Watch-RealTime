@echo off
setlocal
cd /d "%~dp0"
title Storm Watch launcher

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [ERROR] Python 3.10 or newer was not found.
  echo         Install it from https://www.python.org/downloads/ and tick "Add Python to PATH", then run this file again.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required. Your version is:
  %PY% --version
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create the virtual environment.
    pause
    exit /b 1
  )
)

echo Installing dependencies (first run needs internet)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed. Check your internet connection and try again.
  pause
  exit /b 1
)

echo.
echo Starting Storm Watch - your browser should open at http://localhost:8501
echo Press Ctrl+C in this window to stop.
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 (
  echo [ERROR] Storm Watch stopped with an error. See the messages above.
  pause
)
endlocal
