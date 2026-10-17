# Shared launcher bookkeeping. Hold the project mutex while reading/changing records or starting/stopping processes.
$projectRoot = Split-Path -Parent $PSScriptRoot
$processData = Join-Path $projectRoot 'build_tools\data'

# Windows PowerShell's Start-Process rejects inherited Path/PATH duplicates.
# Normalize only this launcher's process environment before creating children.
$launcherPath = [Environment]::GetEnvironmentVariable('Path', 'Process')
[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
[Environment]::SetEnvironmentVariable('Path', $launcherPath, 'Process')

function Invoke-LauncherLock([scriptblock]$Action) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $key = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant()))).Replace('-', '') }
    finally { $sha.Dispose() }
    $mutex = New-Object System.Threading.Mutex($false, "Local\ZmalaCall-$key")
    $acquired = $false
    try {
        try { $acquired = $mutex.WaitOne(120000) }
        catch [System.Threading.AbandonedMutexException] { $acquired = $true }
        if (-not $acquired) { throw 'Another ZmalaCall launcher is still busy. Try again when it finishes.' }
        & $Action
    } finally {
        if ($acquired) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

function Read-ProcessState {
    $file = Join-Path $processData 'processes.json'
    $state = @{}
    if (Test-Path -LiteralPath $file) {
        $saved = Get-Content -Raw -LiteralPath $file | ConvertFrom-Json
        if ($saved) { foreach ($property in $saved.PSObject.Properties) { $state[$property.Name] = $property.Value } }
    }
    return $state
}

function Get-ProcessRecord([string]$Component) {
    if ($Component -eq 'unconfigured') {
        $file = Join-Path $processData 'unconfigured-process.json'
        if (Test-Path -LiteralPath $file) { return Get-Content -Raw -LiteralPath $file | ConvertFrom-Json }
        return $null
    }
    return (Read-ProcessState)[$Component]
}

# Call while holding Invoke-LauncherLock, preserving records for other components.
function Write-ProcessState([string]$File, $Value) {
    # A stopped launcher must not leave half a JSON document for the next one.
    $temporary = $File + '.tmp'
    try {
        $json = ConvertTo-Json -InputObject $Value
        [IO.File]::WriteAllText($temporary, $json, (New-Object Text.UTF8Encoding($false)))
        if ([IO.File]::Exists($File)) { [IO.File]::Replace($temporary, $File, [System.Management.Automation.Language.NullString]::Value) }
        else { [IO.File]::Move($temporary, $File) }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Set-ProcessRecord([string]$Component, $Record) {
    New-Item -ItemType Directory -Force -Path $processData | Out-Null
    if ($Component -eq 'unconfigured') {
        Write-ProcessState (Join-Path $processData 'unconfigured-process.json') $Record
    } else {
        $state = Read-ProcessState
        if ($null -eq $Record) { $state.Remove($Component) }
        else { $state[$Component] = $Record }
        Write-ProcessState (Join-Path $processData 'processes.json') $state
    }
}

function Get-TrackedProcess($Record) {
    if (-not $Record) { return $null }
    $process = Get-Process -Id $Record.id -ErrorAction SilentlyContinue
    if ($process -and $process.Path -eq $Record.path -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $Record.started) { return $process }
    return $null
}

function New-ProcessRecord($Process, [string]$Executable) {
    return @{ id = $Process.Id; path = $Executable; started = $Process.StartTime.ToUniversalTime().Ticks.ToString() }
}

function Stop-Component([string]$Component) {
    $process = Get-TrackedProcess (Get-ProcessRecord $Component)
    if ($process) {
        Stop-Process -Id $process.Id -ErrorAction Stop
        if (-not $process.WaitForExit(5000)) { throw "The $Component process did not stop." }
    }
    Set-ProcessRecord $Component $null
}
