# Read-only publish validation using existing ingest.py FFmpeg command shape.
# Does NOT modify ingest.py. Logs metrics to ../debug-abbe6f.log
param(
    [int]$DurationSec = 30,
    [string]$Source = "rtsp://192.168.1.14:8080/h264.sdp",
    [string]$MediaPath = "cam_bd7aa967",
    [string]$MtxHost = "100.101.127.80"
)

$ErrorActionPreference = "Continue"
$LogPath = Join-Path (Split-Path $PSScriptRoot -Parent) "debug-abbe6f.log"
$EnvFile = Join-Path $PSScriptRoot ".env"

function Load-Env {
    if (-not (Test-Path $EnvFile)) { throw "Missing edge/.env" }
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $val = $matches[2].Trim()
            Set-Item -Path "env:$name" -Value $val
        }
    }
}

function Write-DebugLog($HypothesisId, $Message, $Data) {
    $payload = @{
        sessionId    = "abbe6f"
        hypothesisId = $HypothesisId
        location     = "edge/validate_publish.ps1"
        message      = $Message
        data         = $Data
        timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    } | ConvertTo-Json -Compress
    Add-Content -Path $LogPath -Value $payload -Encoding UTF8
}

Load-Env
$user = $env:MEDIAMTX_PUBLISH_USERNAME
$pass = $env:MEDIAMTX_PUBLISH_PASSWORD
if (-not $user -or -not $pass) { throw "MEDIAMTX publish credentials missing in edge/.env" }

# URL-encode via python to match ingest.py behavior (avoid logging secrets)
$publishUrl = python -c "from urllib.parse import quote; u=quote('$user', safe=''); p=quote('$pass', safe=''); print(f'rtsp://{u}:{p}@${MtxHost}:8554/$MediaPath')"

Write-Host "=== Publish validation ($DurationSec s) path=$MediaPath host=$MtxHost ===" -ForegroundColor Cyan

$ffmpegArgs = @(
    "-hide_banner", "-loglevel", "info", "-nostdin",
    "-rtsp_transport", "tcp", "-fflags", "+genpts",
    "-analyzeduration", "500000", "-probesize", "500000",
    "-i", $Source,
    "-map", "0:v:0", "-c:v", "copy", "-an",
    "-f", "rtsp", "-rtsp_transport", "tcp",
    "-muxdelay", "0", "-flush_packets", "1",
    $publishUrl
)

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "ffmpeg"
$psi.Arguments = ($ffmpegArgs | ForEach-Object { if ($_ -match '\s') { '"{0}"' -f $_ } else { $_ } }) -join ' '
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$p = [System.Diagnostics.Process]::Start($psi)
$stderr = New-Object System.Text.StringBuilder
$timer = [Diagnostics.Stopwatch]::StartNew()
while (-not $p.HasExited -and $timer.Elapsed.TotalSeconds -lt $DurationSec) {
    while ($p.StandardError.Peek() -ge 0) { [void]$stderr.AppendLine($p.StandardError.ReadLine()) }
    Start-Sleep -Milliseconds 200
}
if (-not $p.HasExited) { $p.Kill(); $p.WaitForExit(3000) }
while ($p.StandardError.Peek() -ge 0) { [void]$stderr.AppendLine($p.StandardError.ReadLine()) }
$out = $stderr.ToString()
$elapsed = [math]::Round($timer.Elapsed.TotalSeconds, 2)

$speed = if ($out -match 'speed=\s*([\d.]+)x') { [double]$Matches[1] } else { $null }
$frames = if ($out -match 'frame=\s*(\d+)') { [int]([regex]::Matches($out, 'frame=\s*(\d+)') | Select-Object -Last 1).Groups[1].Value } else { $null }
$timeStr = if ($out -match 'time=\s*([\d:.]+)') { ([regex]::Matches($out, 'time=\s*([\d:.]+)') | Select-Object -Last 1).Groups[1].Value } else { $null }
$fps = if ($frames -and $elapsed -gt 0) { [math]::Round($frames / $elapsed, 2) } else { $null }

Write-Host "Elapsed: ${elapsed}s | frames: $frames | video time: $timeStr | speed: ${speed}x | publish fps: $fps"
Write-DebugLog "H11" "publish validation" @{
    duration_sec = $DurationSec
    elapsed_sec  = $elapsed
    frames       = $frames
    video_time   = "$timeStr"
    speed_x      = $speed
    publish_fps  = $fps
    tailscale    = "direct"
    media_path   = $MediaPath
}

Write-Host "`n--- Reader test (10s) ---"
$readUrl = "rtsp://$MtxHost`:8554/$MediaPath"
$readOut = ffmpeg -hide_banner -loglevel info -rtsp_transport tcp -i $readUrl -map 0:v:0 -t 10 -f null - 2>&1 | Out-String
$readSpeed = if ($readOut -match 'speed=\s*([\d.]+)x') { [double]([regex]::Matches($readOut, 'speed=\s*([\d.]+)x') | Select-Object -Last 1).Groups[1].Value } else { $null }
$readFrames = if ($readOut -match 'frame=\s*(\d+)') { [int]([regex]::Matches($readOut, 'frame=\s*(\d+)') | Select-Object -Last 1).Groups[1].Value } else { $null }
$readFps = if ($readFrames) { [math]::Round($readFrames / 10, 2) } else { $null }
Write-Host "Reader: frames=$readFrames fps~=$readFps speed=${readSpeed}x"
Write-DebugLog "H11" "reader validation" @{ frames = $readFrames; reader_fps = $readFps; speed_x = $readSpeed; url_host = $MtxHost }
