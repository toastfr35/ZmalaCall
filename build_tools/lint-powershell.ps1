# Parse scripts without dot-sourcing them: linting must never start/stop services
# or run installer commands. Git excludes local runtime and scratch directories.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$failed = $false
Push-Location $repoRoot
try {
    $sources = & git ls-files --cached --others --exclude-standard -- '*.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate PowerShell sources with git.' }
    foreach ($source in ($sources | Sort-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $source)) { continue }
        $tokens = $null
        $parseErrors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $repoRoot $source), [ref]$tokens, [ref]$parseErrors)
        foreach ($parseError in $parseErrors) {
            Write-Host "${source}:$($parseError.Extent.StartLineNumber): $($parseError.Message)"
            $failed = $true
        }
    }
} finally {
    Pop-Location
}
if ($failed) { exit 1 }
Write-Host 'PowerShell syntax checks passed.'
