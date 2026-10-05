@echo off
rem Makes Jarvis start silently in the background every time you log in to Windows.
cd /d "%~dp0"
if not exist .venv (
  echo Run install.bat first.
  pause
  exit /b 1
)
set "DIR=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
(
  echo Set sh = CreateObject("WScript.Shell"^)
  echo sh.CurrentDirectory = "%DIR%"
  echo sh.Run """%DIR%.venv\Scripts\pythonw.exe"" ""%DIR%server.py""", 0, False
) > "%STARTUP%\Jarvis.vbs"
echo Jarvis will now start automatically when you log in.
echo To undo, run remove_from_startup.bat
start "" wscript.exe "%STARTUP%\Jarvis.vbs"
echo Started Jarvis in the background: http://localhost:8000
pause
