@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-msys.ps1" %*
exit /b %ERRORLEVEL%

