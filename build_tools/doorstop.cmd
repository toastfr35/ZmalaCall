@echo off
setlocal
set "DOORSTOP_HOME=%~dp0runtime\doorstop\Scripts"
if not exist "%DOORSTOP_HOME%\doorstop.exe" (
    echo Doorstop is not installed. Run build_tools\install-doorstop.ps1 first.
    exit /b 1
)
for %%I in ("%~dp0..") do set "DOORSTOP_PROJECT=%%~fI"
"%DOORSTOP_HOME%\doorstop.exe" %* --project "%DOORSTOP_PROJECT%"
exit /b %ERRORLEVEL%
