# Region publish benchmark — identical FFmpeg command to ingest.py.
# Usage:
#   .\benchmark_region_publish.ps1 -Label sydney -MtxHost 100.101.127.80
#   .\benchmark_region_publish.ps1 -Label mumbai  -MtxHost <mumbai-tailscale-ip>
param(
    [Parameter(Mandatory = $true)]
    [string]$Label,
    [Parameter(Mandatory = $true)]
    [string]$MtxHost,
    [int]$DurationSec = 30,
    [string]$Source = "rtsp://192.168.1.14:8080/h264.sdp",
    [string]$MediaPath = "cam_bd7aa967"
)

$ErrorActionPreference = "Continue"
$LogPath = Join-Path (Split-Path $PSScriptRoot -Parent) "debug-abbe6f.log"
$EnvFile = Join-Path $PSScriptRoot ".env"

function Load-Env {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            Set-Item -Path ("env:" + $matches[1].Trim()) -Value $matches[2].Trim()
        }
    }
}

function Write-DebugLog($Message, $Data) {
    $payload = @{
        sessionId    = "abbe6f"
        hypothesisId = "H12"
        location     = "edge/benchmark_region_publish.ps1"
        message      = $Message
        data         = $Data
        timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    } | ConvertTo-Json -Compress
    Add-Content -Path $LogPath -Value $payload -Encoding UTF8
}

if (-not (Test-Path $EnvFile)) { throw "Missing edge/.env" }
Load-Env

Write-Host "=== Region benchmark [$Label] host=$MtxHost duration=${DurationSec}s ===" -ForegroundColor Cyan

$pingOut = & tailscale ping -c 3 $MtxHost 2>&1 | Out-String
$rtts = [regex]::Matches($pingOut, "in\s+([\d.]+)ms") | ForEach-Object { [double]$_.Groups[1].Value }
$avgRtt = if ($rtts.Count -gt 0) { [math]::Round(($rtts | Measure-Object -Average).Average, 1) } else { $null }
$isDirect = $pingOut -notmatch "via DERP" -and $pingOut -notmatch "direct connection not established"
Write-Host "Tailscale RTT avg: $avgRtt ms | direct: $isDirect"

$pub = python -c @"
import os
from urllib.parse import quote
from dotenv import load_dotenv
load_dotenv(r'$EnvFile')
u = quote(os.environ['MEDIAMTX_PUBLISH_USERNAME'], safe='')
p = quote(os.environ['MEDIAMTX_PUBLISH_PASSWORD'], safe='')
print(f'rtsp://{u}:{p}@${MtxHost}:8554/$MediaPath')
"@

$errFile = Join-Path $env:TEMP "ffmpeg_${Label}_err.txt"
Remove-Item $errFile -ErrorAction SilentlyContinue

$args = @(
    "-hide_banner", "-loglevel", "info", "-nostdin",
    "-rtsp_transport", "tcp", "-fflags", "+genpts",
    "-analyzeduration", "500000", "-probesize", "500000",
    "-i", $Source,
    "-map", "0:v:0", "-c:v", "copy", "-an",
    "-f", "rtsp", "-rtsp_transport", "tcp",
    "-muxdelay", "0", "-flush_packets", "1",
    $pub.Trim()
)

$sw = [Diagnostics.Stopwatch]::StartNew()
$proc = Start-Process -FilePath ffmpeg -ArgumentList $args -RedirectStandardError $errFile -PassThru -NoNewWindow
Start-Sleep -Seconds $DurationSec
if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
$sw.Stop()
$stderr = Get-Content $errFile -Raw -ErrorAction SilentlyContinue

$speedMatches = [regex]::Matches($stderr, "speed=\s*([\d.]+)x")
$speed = if ($speedMatches.Count -gt 0) { [double]$speedMatches[$speedMatches.Count - 1].Groups[1].Value } else { $null }
$frameMatches = [regex]::Matches($stderr, "frame=\s*(\d+)")
$frames = if ($frameMatches.Count -gt 0) { [int]$frameMatches[$frameMatches.Count - 1].Groups[1].Value } else { 0 }
$timeMatches = [regex]::Matches($stderr, "time=\s*([\d:.]+)")
$videoTime = if ($timeMatches.Count -gt 0) { $timeMatches[$timeMatches.Count - 1].Groups[1].Value } else { $null }
$elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 2)
$publishFps = if ($elapsed -gt 0) { [math]::Round($frames / $elapsed, 2) } else { 0 }

Write-Host "Elapsed: ${elapsed}s | frames: $frames | video: $videoTime | speed: ${speed}x | fps: $publishFps"

$result = @{
    label       = $Label
    host        = $MtxHost
    tailscale_direct = $isDirect
    rtt_ms      = $avgRtt
    elapsed_sec = $elapsed
    frames      = $frames
    video_time  = "$videoTime"
    speed_x     = $speed
    publish_fps = $publishFps
}
Write-DebugLog "region publish benchmark" $result

if ($speed -ge 0.9 -and $publishFps -ge 25) {
    Write-Host "PASS: Near real-time for region $Label" -ForegroundColor Green
    exit 0
}
Write-Host "FAIL: Still throttled for region $Label (target ~1.0x / ~30 FPS)" -ForegroundColor Yellow
exit 1
