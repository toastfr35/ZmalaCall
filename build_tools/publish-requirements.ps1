# Run the catalogue publisher with the isolated Doorstop runtime.
$ErrorActionPreference = 'Stop'
$requirementsPython = Join-Path $PSScriptRoot 'runtime/doorstop/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $requirementsPython)) {
    throw 'Run build_tools/install-doorstop.ps1 first.'
}
$temporaryDirectory = Join-Path $PSScriptRoot 'tmp'
New-Item -ItemType Directory -Force -Path $temporaryDirectory | Out-Null
& $requirementsPython (Join-Path $PSScriptRoot 'publish-requirements.py')
if ($LASTEXITCODE -ne 0) { throw 'Publishing requirements failed.' }
