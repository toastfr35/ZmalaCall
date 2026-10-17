@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_tools\start-terminal.ps1" %*
if errorlevel 1 (
    pause
    exit /b 1
)
exit /b 0
