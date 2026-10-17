# Integration check: briefly starts/stops the real Windows applications.
# Requires managed terminals to be stopped; restores the server's initial state.
$ErrorActionPreference = 'Stop'
$toolsRoot = Split-Path -Parent $PSScriptRoot
. "$toolsRoot\processes.ps1"
if ((Get-TrackedProcess (Get-ProcessRecord 'terminal')) -or (Get-TrackedProcess (Get-ProcessRecord 'unconfigured'))) {
    throw 'Close the managed terminals before running this check.'
}
$serverWasRunning = [bool](Get-TrackedProcess (Get-ProcessRecord 'server'))
$savedPython = $env:VIDEOCALL_PYTHON
function Assert-Check($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Run-Launcher([string]$Name, [string[]]$Options = @()) {
    & (Join-Path $projectRoot $Name) @Options
    Assert-Check ($LASTEXITCODE -eq 0) "$Name failed."
}
function Assert-Running([string]$Component, [int]$ExpectedId = 0) {
    $process = Get-TrackedProcess (Get-ProcessRecord $Component)
    Assert-Check ([bool]$process) "$Component is not running."
    if ($ExpectedId) { Assert-Check ($process.Id -eq $ExpectedId) "$Component was replaced unexpectedly." }
    return $process.Id
}
try {
    # Node-only startup must work even with an invalid terminal Python override.
    $env:VIDEOCALL_PYTHON = 'C:\missing-zmalacall-test-python.exe'
    Run-Launcher 'Start ZmalaCall Server.cmd' @('-NoBrowser')
    $serverId = Assert-Running 'server'
    Run-Launcher 'Start ZmalaCall Server.cmd' @('-NoBrowser')
    Assert-Running 'server' $serverId | Out-Null
    Run-Launcher 'Stop ZmalaCall Terminal.cmd'
    Run-Launcher 'Stop ZmalaCall Terminal.cmd'
    Assert-Running 'server' $serverId | Out-Null
    Run-Launcher 'Stop ZmalaCall Server.cmd'
    Run-Launcher 'Stop ZmalaCall Server.cmd'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'server'))) 'Server did not stop.'

    $env:VIDEOCALL_PYTHON = $savedPython
    Run-Launcher 'Start ZmalaCall Terminal.cmd'
    Start-Sleep -Seconds 2
    $terminalId = Assert-Running 'terminal'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'server'))) 'Terminal implicitly started the server.'
    Run-Launcher 'Start ZmalaCall Terminal.cmd'
    Assert-Running 'terminal' $terminalId | Out-Null
    Run-Launcher 'Start ZmalaCall Server.cmd' @('-NoBrowser')
    Assert-Running 'terminal' $terminalId | Out-Null
    Assert-Check ((Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 2).ok) 'Server is unhealthy.'
    Run-Launcher 'Stop ZmalaCall Server.cmd'
    Assert-Running 'terminal' $terminalId | Out-Null
    Run-Launcher 'Start ZmalaCall Terminal Unconfigured.cmd'
    Start-Sleep -Seconds 2
    $unconfiguredId = Assert-Running 'unconfigured'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'server'))) 'Unconfigured terminal implicitly started the server.'
    Assert-Running 'terminal' $terminalId | Out-Null
    Run-Launcher 'Start ZmalaCall Terminal Unconfigured.cmd'
    Assert-Running 'unconfigured' $unconfiguredId | Out-Null
    Run-Launcher 'Stop ZmalaCall Terminal.cmd'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'terminal'))) 'Regular terminal did not stop.'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'unconfigured'))) 'Unconfigured terminal did not stop.'
    Run-Launcher 'Stop ZmalaCall Terminal.cmd'
    Write-Host 'PASS: all five CMD launchers, independent process control, duplicate starts, repeated stops and Node-only server startup.'
} finally {
    $env:VIDEOCALL_PYTHON = $savedPython
    & "$toolsRoot\stop-terminal.ps1"
    if ($serverWasRunning) { & "$toolsRoot\start-server.ps1" -NoBrowser }
    else { & "$toolsRoot\stop-server.ps1" }
}
