#!/usr/bin/env bash
# Read-only AWS EC2 network diagnostics for Tailscale direct-connect troubleshooting.
# Run on the Sydney EC2 instance via SSH. Does NOT modify firewall or SG rules.
set -euo pipefail

echo "========== HOST =========="
hostname
date -u

echo
echo "========== TAILSCALE STATUS =========="
sudo tailscale status || true
sudo tailscale status --json 2>/dev/null | head -c 4000 || true

echo
echo "========== TAILSCALE NETCHECK =========="
sudo tailscale netcheck || true

echo
echo "========== UDP LISTENERS =========="
sudo ss -lunp | grep -E '41641|tailscale|State' || sudo ss -lunp

echo
echo "========== TAILSCALE INTERFACE =========="
ip -brief addr show tailscale0 2>/dev/null || true

echo
echo "========== ROUTING (read-only) =========="
ip route show default 2>/dev/null || true
ip route show dev tailscale0 2>/dev/null || true

echo
echo "========== UFW / IPTABLES (read-only) =========="
sudo ufw status verbose 2>/dev/null || echo "ufw not active"
sudo iptables -L INPUT -n --line-numbers 2>/dev/null | head -30 || true

echo
echo "========== RTSP LISTENERS (should NOT be public) =========="
sudo ss -ltnp | grep -E ':8554|:8888|:8889|:9997' || echo "no matching listeners"

echo
echo "========== PING WINDOWS PEER =========="
sudo tailscale ping --verbose 100.111.90.39 || true

echo
echo "========== DONE =========="
echo "Review Security Group manually in AWS Console:"
echo "  - REMOVE temporary inbound TCP 8554 from public IP if still present"
echo "  - For direct Tailscale: inbound UDP 41641 required on EC2 (WireGuard listen port)"
echo "    Reason: peers initiate UDP to 41641 for hole punching; source IP is dynamic."
