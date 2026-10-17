# Stop the tracked normal and QR-test profiles without affecting the server.
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\processes.ps1"
Invoke-LauncherLock {
    Stop-Component 'terminal'
    Stop-Component 'unconfigured'
    Write-Host 'ZmalaCall terminals stopped.'
}
