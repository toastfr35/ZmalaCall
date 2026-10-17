# Locate a compatible Windows Python for the terminal; imported by launchers without starting the app.
$ErrorActionPreference = 'Stop'
function Find-TerminalPython {
    $probeFile = Join-Path $PSScriptRoot 'check-python.py'
    $failures = @()
    if ($env:VIDEOCALL_PYTHON) { $candidates = @($env:VIDEOCALL_PYTHON) }
    else { $candidates = @('C:\msys64\ucrt64\bin\python.exe', (Get-Command python.exe -ErrorAction SilentlyContinue).Source) }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            $probe = New-Object System.Diagnostics.Process
            try {
                $probe.StartInfo.FileName = (Resolve-Path -LiteralPath $candidate).ProviderPath
                $probe.StartInfo.Arguments = '"' + $probeFile + '"'
                $probe.StartInfo.UseShellExecute = $false
                $probe.StartInfo.CreateNoWindow = $true
                $probe.StartInfo.RedirectStandardOutput = $true
                $probe.StartInfo.RedirectStandardError = $true
                $probe.Start() | Out-Null
                if (-not $probe.WaitForExit(10000)) {
                    $probe.Kill()
                    $failures += "${candidate}: Python check timed out."
                    continue
                }
                if ($probe.ExitCode -eq 0) { return $probe.StartInfo.FileName }
                $failures += "${candidate}: $($probe.StandardError.ReadToEnd().Trim())"
            } catch {
                $failures += "${candidate}: $($_.Exception.Message)"
            } finally {
                $probe.Dispose()
            }
        } elseif ($candidate) {
            $failures += "${candidate}: File not found."
        }
    }
    throw ("64-bit Windows Python with Tkinter is required. Set VIDEOCALL_PYTHON to its executable path.`n" + ($failures -join "`n"))
}
