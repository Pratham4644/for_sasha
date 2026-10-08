# Network A/B test — run on HOME ISP first, then repeat on PHONE HOTSPOT.
# Does NOT modify application code. Logs evidence to ../debug-abbe6f.log
param(
    [string]$Label = "home-isp",
    [string]$AwsTailscaleIp = "100.101.127.80"
)

$ErrorActionPreference = "Continue"
$LogPath = Join-Path (Split-Path $PSScriptRoot -Parent) "debug-abbe6f.log"
$Ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()

function Write-DebugLog {
    param([string]$HypothesisId, [string]$Message, [hashtable]$Data)
    $payload = @{
        sessionId    = "abbe6f"
        hypothesisId = $HypothesisId
        location     = "edge/network_ab_test.ps1"
        message      = $Message
        data         = $Data
        timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    } | ConvertTo-Json -Compress
    Add-Content -Path $LogPath -Value $payload -Encoding UTF8
}

Write-Host "=== Network A/B Test [$Label] ===" -ForegroundColor Cyan

$gateway = (Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1).NextHop
Write-Host "Default gateway: $gateway"

Write-DebugLog "H7" "ab test start" @{
    label           = $Label
    gateway         = $gateway
    aws_tailscale_ip = $AwsTailscaleIp
}

Write-Host "`n--- tailscale netcheck ---"
$netcheck = & tailscale netcheck 2>&1 | Out-String
Write-Host $netcheck
$portMapping = if ($netcheck -match "PortMapping:\s*(.+)") { $Matches[1].Trim() } else { "unknown" }
Write-DebugLog "H7" "netcheck" @{ label = $Label; port_mapping = $portMapping; snippet = $netcheck.Substring(0, [Math]::Min(800, $netcheck.Length)) }

Write-Host "`n--- tailscale status ---"
$status = & tailscale status 2>&1 | Out-String
Write-Host $status
$usesDerp = $status -match "relay"
Write-DebugLog "H7" "status" @{ label = $Label; uses_derp = [bool]$usesDerp; snippet = $status.Trim() }

Write-Host "`n--- tailscale ping --until-direct (25s) ---"
$pingOut = & tailscale ping --until-direct --timeout 25s $AwsTailscaleIp 2>&1 | Out-String
Write-Host $pingOut
$direct = $pingOut -notmatch "direct connection not established"
$rtts = [regex]::Matches($pingOut, "in\s+([\d.]+)ms") | ForEach-Object { [double]$_.Groups[1].Value }
$avgRtt = if ($rtts.Count -gt 0) { [math]::Round(($rtts | Measure-Object -Average).Average, 1) } else { $null }
Write-DebugLog "H7" "ping until direct" @{
    label         = $Label
    direct        = $direct
    avg_rtt_ms    = $avgRtt
    via_derp      = ($pingOut -match "via DERP")
}

Write-Host "`n--- tailscale status --json (peer CurAddr) ---"
try {
    $json = & tailscale status --json 2>&1 | Out-String | ConvertFrom-Json
    $peer = $json.Peer.PSObject.Properties | ForEach-Object { $_.Value } | Where-Object { $_.TailscaleIPs -contains $AwsTailscaleIp } | Select-Object -First 1
    $self = $json.Self
    Write-Host "Self CurAddr: $($self.CurAddr) Relay: $($self.Relay) Active: $($self.Active)"
    Write-Host "Peer CurAddr: $($peer.CurAddr) Relay: $($peer.Relay) Active: $($peer.Active)"
    Write-DebugLog "H7" "json endpoints" @{
        label          = $Label
        self_cur_addr  = "$($self.CurAddr)"
        self_relay     = "$($self.Relay)"
        peer_cur_addr  = "$($peer.CurAddr)"
        peer_relay     = "$($peer.Relay)"
    }
} catch {
    Write-Host "JSON parse failed: $_"
}

Write-Host "`n=== SUMMARY [$Label] ===" -ForegroundColor Yellow
Write-Host "Direct established: $direct"
Write-Host "Avg RTT: $avgRtt ms"
Write-Host "PortMapping: $portMapping"
if (-not $direct) {
    Write-Host "NEXT: If on home ISP, repeat this script on phone hotspot:" -ForegroundColor Magenta
    Write-Host "  .\network_ab_test.ps1 -Label phone-hotspot"
    Write-Host "If hotspot gets DIRECT but home does not -> router/ISP NAT is the blocker."
    Write-Host "Also ensure AWS SG allows inbound UDP 41641 to EC2."
}
