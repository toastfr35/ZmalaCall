# Start or reuse the tracked server under the launcher lock; optionally open its private admin shortcut.
param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\processes.ps1"
Invoke-LauncherLock {
    New-Item -ItemType Directory -Force -Path "$projectRoot\zmala_server\data" | Out-Null
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $process = Get-TrackedProcess (Get-ProcessRecord 'server')
    $launched = $false
    if (-not $process) {
        if (-not (Test-Path -LiteralPath "$projectRoot\zmala_server\node_modules\sip\sip.js") -or
            -not (Test-Path -LiteralPath "$projectRoot\zmala_server\node_modules\qrcode\package.json") -or
            -not (Test-Path -LiteralPath "$projectRoot\zmala_server\node_modules\pdfkit\package.json") -or
            -not (Test-Path -LiteralPath "$projectRoot\zmala_server\node_modules\nodemailer\package.json")) {
            & npm.cmd --prefix "$projectRoot\zmala_server" ci --cache "$projectRoot\build_tools\.npm-cache" --ignore-scripts
            if ($LASTEXITCODE -ne 0) { throw 'Server dependency installation failed.' }
        }
        $process = Start-Process -FilePath $node -ArgumentList @('"' + "$projectRoot\zmala_server\main.js" + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput "$projectRoot\zmala_server\data\server.log" -RedirectStandardError "$projectRoot\zmala_server\data\server-error.log" -PassThru
        Set-ProcessRecord 'server' (New-ProcessRecord $process $node)
        $launched = $true
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $process.Refresh()
        if ($process.HasExited) { break }
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 1
            if ($health.ok) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) {
        if ($launched) { Stop-Component 'server' }
        throw 'The server did not start. Check zmala_server/data/server-error.log (ports 5060 and 8080 may already be in use).'
    }
    if (-not $NoBrowser) { Start-Process -FilePath "$projectRoot\zmala_server\data\open-admin.url" }
    Write-Host 'ZmalaCall server is running. Administration: zmala_server/data/open-admin.url.'
}
