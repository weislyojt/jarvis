@echo off
rem Stops background Jarvis and removes it from Windows startup.
set "DIR=%~dp0"
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.vbs" 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*%DIR%server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Jarvis stopped and removed from startup.
pause
