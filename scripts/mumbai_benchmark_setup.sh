#!/usr/bin/env bash
# Minimal Mumbai RTSP benchmark node (ap-south-1). Network test only — not full production.
# Run on a fresh Ubuntu 22.04/24.04 EC2 in Mumbai after cloning this repo.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/camera-platform}"
MEDIAMTX_ONLY=1

echo "========== Mumbai benchmark setup =========="
hostname
date -u

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" || true
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Installing Tailscale..."
  curl -fsSL https://tailscale.com/install.sh | sh
  echo "Run: sudo tailscale up   (join same tailnet as Sydney + Windows edge)"
fi

if [ ! -d "$REPO_DIR" ]; then
  echo "Clone repo first:"
  echo "  git clone https://github.com/Pratham4644/for_sasha.git $REPO_DIR"
  exit 1
fi

cd "$REPO_DIR"
git pull origin main || true

echo
echo "========== Security Group checklist (AWS Console, Mumbai EC2) =========="
echo "  ADD:    UDP 41641 inbound (Tailscale WireGuard direct)"
echo "  DO NOT expose 8554/8888/8889/9997 to 0.0.0.0/0"
echo "  Optional: restrict 8554 to Tailscale CGNAT 100.64.0.0/10 only"

echo
echo "========== Start MediaMTX only (docker) =========="
sudo docker compose up -d mediamtx
sleep 3
sudo docker ps --filter name=mediamtx
sudo ss -ltnp | grep -E ':8554|:9997' || true

TS_IP=$(tailscale ip -4 2>/dev/null || echo "NOT_JOINED")
echo
echo "========== Tailscale IP (use for benchmark) =========="
echo "  Mumbai Tailscale IP: $TS_IP"

echo
echo "========== From Windows edge, run =========="
echo "  powershell -ExecutionPolicy Bypass -File edge/benchmark_region_publish.ps1 -Label sydney -MtxHost 100.101.127.80"
echo "  powershell -ExecutionPolicy Bypass -File edge/benchmark_region_publish.ps1 -Label mumbai  -MtxHost $TS_IP"
echo
echo "Target: FFmpeg speed ~1.0x, publish_fps ~30 (Sydney baseline is ~0.11x / ~2.5 FPS)"
