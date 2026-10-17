# Delegate to the shared launcher with a separate QR-enrollment test profile.
param([switch]$Fullscreen, [switch]$ConnectWifi)
& "$PSScriptRoot\start-terminal.ps1" -Unconfigured -Fullscreen:$Fullscreen -ConnectWifi:$ConnectWifi
