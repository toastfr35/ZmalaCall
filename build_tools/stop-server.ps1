# Stop only the tracked server; process identity checks protect unrelated processes.
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\processes.ps1"
Invoke-LauncherLock {
    Stop-Component 'server'
    Write-Host 'ZmalaCall server stopped.'
}
