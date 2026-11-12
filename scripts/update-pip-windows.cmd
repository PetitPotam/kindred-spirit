@echo off
rem Double-click to update Kindred Spirit (Pip) on this PC: gets the latest version, builds it, installs it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-pip-windows.ps1"
echo.
pause
