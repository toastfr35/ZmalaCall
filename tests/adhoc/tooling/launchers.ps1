# Integration check: briefly starts/stops the real Windows applications.
# Requires managed terminals to be stopped; leaves other processes alone.
$ErrorActionPreference = 'Stop'
$toolsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../build_tools'))
. "$toolsRoot\processes.ps1"
if ((Get-TrackedProcess (Get-ProcessRecord 'terminal')) -or (Get-TrackedProcess (Get-ProcessRecord 'unconfigured'))) {
    throw 'Close the managed terminals before running this check.'
}
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
    $env:VIDEOCALL_PYTHON = $savedPython
    Run-Launcher 'Start ZmalaCall Terminal.cmd'
    Start-Sleep -Seconds 2
    $terminalId = Assert-Running 'terminal'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'server'))) 'Terminal implicitly started the server.'
    Run-Launcher 'Start ZmalaCall Terminal.cmd'
    Assert-Running 'terminal' $terminalId | Out-Null
    Run-Launcher 'Start ZmalaCall Terminal.cmd' @('-Unconfigured')
    Start-Sleep -Seconds 2
    $unconfiguredId = Assert-Running 'unconfigured'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'server'))) 'Unconfigured terminal implicitly started the server.'
    Assert-Running 'terminal' $terminalId | Out-Null
    Run-Launcher 'Start ZmalaCall Terminal.cmd' @('-Unconfigured')
    Assert-Running 'unconfigured' $unconfiguredId | Out-Null
    Run-Launcher 'Stop ZmalaCall Terminal.cmd'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'terminal'))) 'Regular terminal did not stop.'
    Assert-Check (-not (Get-TrackedProcess (Get-ProcessRecord 'unconfigured'))) 'Unconfigured terminal did not stop.'
    Run-Launcher 'Stop ZmalaCall Terminal.cmd'
    Write-Host 'PASS: terminal CMD launchers, independent process control, duplicate starts, repeated stops.'
} finally {
    $env:VIDEOCALL_PYTHON = $savedPython
    & "$toolsRoot\stop-terminal.ps1"
}
