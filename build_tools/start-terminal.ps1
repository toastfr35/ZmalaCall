# Prepare the Windows runtime and start/reuse the requested terminal profile under the launcher lock.
param([switch]$Fullscreen, [switch]$Unconfigured, [switch]$ConnectWifi)
$ErrorActionPreference = 'Stop'
if ($ConnectWifi -and -not $Unconfigured) { throw '-ConnectWifi is only available for an unconfigured terminal.' }
. "$PSScriptRoot\processes.ps1"
Invoke-LauncherLock {
    $component = if ($Unconfigured) { 'unconfigured' } else { 'terminal' }
    $label = if ($Unconfigured) { 'unconfigured terminal' } else { 'terminal' }
    if (Get-TrackedProcess (Get-ProcessRecord $component)) {
        Write-Host "The $label is already running. Use Alt+Tab to find it."
        return
    }
    . "$PSScriptRoot\python.ps1"
    $terminalPython = Find-TerminalPython
    New-Item -ItemType Directory -Force -Path "$projectRoot\zmala_terminal\data" | Out-Null
    if (-not (Test-Path -LiteralPath "$projectRoot\build_tools\runtime\linphone\linphone-sdk\win64\bin\openh264.dll") -or
        -not (Test-Path -LiteralPath "$projectRoot\build_tools\runtime\angle-desktop\runtimes\win-x64\native\libEGL.dll")) {
        & $terminalPython "$PSScriptRoot\setup-runtime.py"
        if ($LASTEXITCODE -ne 0) { throw 'Terminal runtime setup failed.' }
    }
    if (-not (Test-Path -LiteralPath "$projectRoot\build_tools\runtime\zmala-qr-preview.dll") -or
        (Get-Item -LiteralPath "$projectRoot\build_tools\native\qr_preview.c").LastWriteTimeUtc -gt
        (Get-Item -LiteralPath "$projectRoot\build_tools\runtime\zmala-qr-preview.dll").LastWriteTimeUtc) {
        & $terminalPython "$PSScriptRoot\build-qr-preview.py"
        if ($LASTEXITCODE -ne 0) { throw 'Camera QR preview adapter setup failed.' }
    }
    if (-not (Test-Path -LiteralPath "$projectRoot\build_tools\runtime\zmala-h264-decoder.dll") -or
        (Get-Item -LiteralPath "$projectRoot\build_tools\native\h264_decoder.c").LastWriteTimeUtc -gt
        (Get-Item -LiteralPath "$projectRoot\build_tools\runtime\zmala-h264-decoder.dll").LastWriteTimeUtc) {
        & $terminalPython "$PSScriptRoot\build-h264-decoder.py"
        if ($LASTEXITCODE -ne 0) { throw 'H.264 decoder adapter setup failed.' }
    }
    $windowPython = Join-Path (Split-Path -Parent $terminalPython) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $windowPython)) { $windowPython = $terminalPython }
    $arguments = @('"' + "$projectRoot\zmala_terminal\main.py" + '"')
    $logPrefix = 'terminal'
    if ($Unconfigured) {
        $arguments += @('--profile', 'unconfigured', '--unconfigured', '--wifi-mode')
        $arguments += if ($ConnectWifi) { 'connect' } else { 'existing-link' }
        $logPrefix = 'unconfigured'
    }
    if ($Fullscreen) { $arguments += '--fullscreen' }
    $process = Start-Process -FilePath $windowPython -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Normal -RedirectStandardOutput "$projectRoot\zmala_terminal\data\$logPrefix-native.log" -RedirectStandardError "$projectRoot\zmala_terminal\data\$logPrefix-error.log" -PassThru
    Set-ProcessRecord $component (New-ProcessRecord $process $windowPython)
    Start-Sleep -Milliseconds 800
    $process.Refresh()
    if ($process.HasExited) {
        Set-ProcessRecord $component $null
        throw "The terminal did not start. Check zmala_terminal/data/$logPrefix-error.log."
    }
    Write-Host "ZmalaCall $label started. Use Alt+Tab to find its window."
    if ($Unconfigured -and -not $ConnectWifi) { Write-Host 'Wi-Fi test mode uses this PC''s existing network connection.' }
}
