# Compile Nano firmware artifacts for the selected bootloader; uploading uses a separate workflow.
param(
    [ValidateSet('atmega328', 'atmega328old')]
    [string]$Processor = 'atmega328'
)

$ErrorActionPreference = 'Stop'
$keypadRoot = Split-Path -Parent $PSScriptRoot
$keypadRuntime = Join-Path $PSScriptRoot 'runtime/arduino'
$keypadCli = Join-Path $keypadRuntime 'arduino-cli.exe'
if (-not (Test-Path -LiteralPath $keypadCli)) {
    $keypadCommand = Get-Command arduino-cli -ErrorAction SilentlyContinue
    if (-not $keypadCommand) {
        throw 'Install Arduino CLI or use Arduino IDE as described in keypad/spec.md.'
    }
    $keypadCli = $keypadCommand.Source
}

# Keep the compiler, cores, cache and output within this checkout. JSON-quoted
# paths are valid YAML scalars and handle workspace names containing spaces.
New-Item -ItemType Directory -Force -Path $keypadRuntime | Out-Null
$keypadConfig = Join-Path $keypadRuntime 'arduino-cli.yaml'
$keypadData = (Join-Path $keypadRuntime 'data') | ConvertTo-Json -Compress
$keypadDownloads = (Join-Path $keypadRuntime 'downloads') | ConvertTo-Json -Compress
$keypadUser = (Join-Path $keypadRuntime 'user') | ConvertTo-Json -Compress
@"
directories:
  data: $keypadData
  downloads: $keypadDownloads
  user: $keypadUser
updater:
  enable_notification: false
"@ | Set-Content -LiteralPath $keypadConfig -Encoding utf8

$keypadCommon = @('--config-file', $keypadConfig)
& $keypadCli @keypadCommon core install arduino:avr@1.8.8
if ($LASTEXITCODE -ne 0) { throw 'Arduino AVR core installation failed.' }

$keypadSketch = Join-Path $keypadRoot 'keypad/firmware/ZmalaCallKeypad'
$keypadBuild = Join-Path $PSScriptRoot "tmp/keypad/avr-$Processor"
$keypadOutput = Join-Path $PSScriptRoot "dist/keypad/$Processor"
& $keypadCli @keypadCommon compile --fqbn "arduino:avr:nano:cpu=$Processor" `
    --warnings all --build-path $keypadBuild --output-dir $keypadOutput $keypadSketch
if ($LASTEXITCODE -ne 0) { throw 'Keypad compilation failed.' }
Write-Output "Compiled firmware: $keypadOutput"
