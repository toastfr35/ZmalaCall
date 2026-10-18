# Exercise real stop CMD scripts against isolated processes, without stopping
# the user's live server or opening terminal windows.
$ErrorActionPreference = 'Stop'
$toolsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../build_tools'))
$realRoot = Split-Path -Parent $toolsRoot
$fixture = Join-Path $toolsRoot ('tmp\process-control-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path "$fixture\build_tools", "$fixture\build_tools\data" | Out-Null
foreach ($name in @('processes.ps1', 'stop-terminal.ps1')) {
    Copy-Item -LiteralPath (Join-Path $toolsRoot $name) -Destination "$fixture\build_tools\$name"
}
foreach ($name in @('Stop ZmalaCall Terminal.cmd')) {
    Copy-Item -LiteralPath (Join-Path $realRoot $name) -Destination (Join-Path $fixture $name)
}
'Start-Sleep -Seconds 120' | Set-Content -LiteralPath "$fixture\sleeper.ps1"
. "$fixture\build_tools\processes.ps1"
$executable = (Get-Command powershell.exe).Source
$children = @()
function Assert-Check($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Start-Sleeper([string]$Component) {
    $child = Start-Process -FilePath $executable -ArgumentList @('-NoProfile', '-File', ('"' + "$fixture\sleeper.ps1" + '"')) -WindowStyle Hidden -PassThru
    Invoke-LauncherLock { Set-ProcessRecord $Component (New-ProcessRecord $child $executable) }
    return $child
}
function Run-Stop([string]$Component) {
    & (Join-Path $fixture "Stop ZmalaCall $Component.cmd")
    Assert-Check ($LASTEXITCODE -eq 0) "Stop $Component failed."
}
try {
    $server = Start-Sleeper 'server'; $children += $server
    $terminal = Start-Sleeper 'terminal'; $children += $terminal
    $unconfigured = Start-Sleeper 'unconfigured'; $children += $unconfigured
    Run-Stop 'Terminal'
    $terminal.Refresh(); $unconfigured.Refresh()
    Assert-Check ($terminal.HasExited -and $unconfigured.HasExited) 'Stop Terminal did not stop both profiles.'
    Assert-Check ([bool](Get-TrackedProcess (Get-ProcessRecord 'server'))) 'Stopping terminals stopped server.'
    Run-Stop 'Terminal'

    # A reused PID with a different start time must not kill another process.
    $staleRecord = New-ProcessRecord $server $executable
    $staleRecord.started = '0'
    Invoke-LauncherLock { Set-ProcessRecord 'terminal' $staleRecord }
    Run-Stop 'Terminal'
    Assert-Check ([bool](Get-TrackedProcess (Get-ProcessRecord 'server'))) 'A stale PID killed an unrelated process.'
    Assert-Check (-not (Get-ProcessRecord 'terminal')) 'Stale terminal record was not cleared.'
    Write-Host 'PASS: terminal stop CMD script, both terminal profiles, repeated stops, state preservation and stale-PID protection.'
} finally {
    foreach ($child in $children) {
        $child.Refresh()
        if (-not $child.HasExited) { Stop-Process -Id $child.Id -ErrorAction SilentlyContinue }
    }
}
