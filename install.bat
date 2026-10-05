@echo off
title Jarvis installer
cd /d "%~dp0"
echo.
echo === Installing Jarvis ===
echo.
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python was not found. Install Python 3.11 or newer from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during install. Then run this again.
  pause
  exit /b 1
)
%PY% --version
if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv || (echo Could not create the environment. & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
echo Installing packages...
pip install -r requirements.txt || (echo Package install failed. Check your internet and try again. & pause & exit /b 1)
python configure.py
echo.
echo All set. Double-click start_jarvis.bat to wake Jarvis up.
pause
