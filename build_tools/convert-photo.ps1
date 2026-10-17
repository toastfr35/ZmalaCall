# Convert an input photo to a bounded account asset using the local image tooling.
param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$image = [System.Drawing.Image]::FromFile($Source)
try {
    if ([long]$image.Width * $image.Height -gt 16000000 -or [Math]::Max($image.Width, $image.Height) -gt 8192) {
        throw 'Photo dimensions exceed the supported limit'
    }
    $ratio = [Math]::Min(1.0, 480.0 / [Math]::Max($image.Width, $image.Height))
    $bitmap = New-Object System.Drawing.Bitmap ([Math]::Max(1, [int]($image.Width * $ratio))), ([Math]::Max(1, [int]($image.Height * $ratio)))
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.DrawImage($image, 0, 0, $bitmap.Width, $bitmap.Height)
        } finally { $graphics.Dispose() }
        $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $bitmap.Dispose() }
} finally { $image.Dispose() }
