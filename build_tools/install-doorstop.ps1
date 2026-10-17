# Install the pinned requirements tooling in the project runtime, separate from terminal Python.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath
if (-not (Get-Command uv.exe -ErrorAction SilentlyContinue)) {
    throw 'uv is required to install the dedicated Doorstop environment.'
}
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot 'runtime/uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot 'runtime/python'
$requirementsPython = Join-Path $PSScriptRoot 'runtime/doorstop/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $requirementsPython)) {
    & uv venv --python 3.13 --managed-python (Join-Path $PSScriptRoot 'runtime/doorstop')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Doorstop Python environment.' }
}
& uv pip install --python $requirementsPython --requirement (Join-Path $PSScriptRoot 'doorstop-requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install Doorstop.' }
& (Join-Path $PSScriptRoot 'doorstop.cmd') --version
if ($LASTEXITCODE -ne 0) { throw 'Doorstop installation check failed.' }
