# Network Test Report — Tailscale Direct Connectivity

**Date:** 2026-10-08  
**Edge:** Windows `100.111.90.39` (India, LAN `192.168.1.11`)  
**AWS:** EC2 Sydney `100.101.127.80` / public `3.26.96.100`  
**Camera path:** `cam_bd7aa967`  
**Application code:** unchanged (ingest/MediaMTX/WebRTC/YOLO not modified)

---

## 1. CURRENT NETWORK STATE

| Parameter | Before (DERP) | After direct (2026-10-08 14:23 IST) |
|-----------|---------------|----------------------------------------|
| Tailscale path | DERP relay `"syd"` | **Direct** `3.26.96.100:41641` |
| Direct peer | No | **Yes** (`"direct": true` in debug log) |
| Tailscale RTT | ~393–550 ms | **~317–387 ms** (ping via direct) |
| Nearest DERP (Windows) | Bengaluru (~74 ms to relay, not to peer) |
| UDP available | Yes |
| Router UPnP/NAT-PMP | **None** (`PortMapping:` empty) |
| TCP to MediaMTX via Tailscale | Reachable (`100.101.127.80:8554`) |
| Windows Tailscale firewall | Inbound Allow rules present |

---

## 2. DIRECT CONNECTION TEST

**Result: FAILED** (reconfirmed 2026-10-08 14:04 IST)

**Evidence (2026-10-08, Windows edge — `network_ab_test.ps1 home-isp-repro`):**

```
tailscale status:
  100.101.127.80  ip-172-31-25-239  active; relay "syd"

tailscale ping --verbose 100.101.127.80:
  pong ... via DERP(syd) in 399-478ms (10 samples)
  direct connection not established

tailscale ping --until-direct --timeout 25s 100.101.127.80:
  10x via DERP(syd), avg ~429ms
  direct connection not established

tailscale status --json:
  Self  CurAddr="" Relay=blr Active=false
  Peer  CurAddr="" Relay=syd Active=true   ← both sides lack direct endpoint
```

**Interpretation:** Empty `CurAddr` on **both** peers means UDP hole punching failed end-to-end. Likely causes:
- AWS EC2 missing inbound **UDP 41641** (most common for servers)
- Windows router: **no UPnP** (`PortMapping` empty) — cannot receive inbound UDP

**AWS-side diagnostics:** Not run from this session — SSH to `ubuntu@100.101.127.80` failed (no key on this machine). Run on EC2:

```bash
bash scripts/aws_network_diagnostics.sh
```

---

## 3. STREAM A/B TEST (Direct vs DERP)

**After-direct validation completed** — same FFmpeg command as `ingest.py`, path `cam_bd7aa967`, 30 s wall clock.

| Metric | Baseline (DERP) | After direct | Target |
|--------|-----------------|--------------|--------|
| Tailscale path | DERP ~400 ms | **Direct** ~317–387 ms | Direct |
| Camera input FPS | ~30 | **~30** (242 frames / 8 s) | ~30 |
| FFmpeg publish speed | 0.05–0.12x | **~0.10–0.11x** | ~1.0x |
| Publish FPS | ~1–3 | **~2.5–2.7** | ~30 |
| Frames (30 s wall) | ~39–102 | **71–77** | ~900 |
| Video time (30 s wall) | ~1.6–3.7 s | **~2.6–2.8 s** | ~30 s |

**Log evidence (`debug-abbe6f.log`):**

- H7 `network_ab_test.ps1`: `"direct": true`, `"via_derp": false`, `avg_rtt_ms`: 387
- H11 `validate_after_direct`: `publish_speed_x`: 0.1, `publish_fps`: 2.7, `verdict`: STILL_SLOW
- H12 `benchmark_region_publish.ps1` (sydney-verify): `speed_x`: 0.111, `publish_fps`: 2.56, `rtt_ms`: 331

**Conclusion:** DERP elimination did **not** restore real-time streaming. India → Sydney WAN RTT (~320 ms) remains the bottleneck for RTSP/TCP H.264.

---

## 4. HOTSPOT TEST

**Not performed in this session** — requires manual network switch.

| Network | DERP / Direct | RTT |
|---------|---------------|-----|
| Home ISP | DERP (confirmed) | ~420 ms |
| Phone hotspot | *Pending* | *Pending* |

**Procedure:** disconnect home Wi‑Fi → phone hotspot → reconnect Tailscale → `tailscale ping --until-direct 100.101.127.80`.

---

## 5. SYDNEY VS MUMBAI

**Sydney baseline recorded.** Mumbai benchmark **pending** — provision minimal EC2 in `ap-south-1` and run `edge/benchmark_region_publish.ps1`.

Setup: `scripts/mumbai_benchmark_setup.sh` on Mumbai EC2.

---

## 6. ROOT CAUSE (evidence-based)

**Primary:** Real-time RTSP/TCP video publish collapses on the **India → AWS Sydney WAN** due to high RTT (~320–420 ms), severe TCP reordering, and ~25–31 kbps effective delivery rate (prior `ss -tin` captures).

**Contributing (confirmed today):**

1. Tailscale **cannot establish direct WireGuard** — all traffic via DERP Sydney relay.
2. Windows router reports **no UPnP/NAT-PMP** — likely blocks UDP hole punching from edge.
3. Geographic path India ↔ Sydney remains poor even on public IP (prior A/B).

**Not root cause:** camera, FFmpeg input, timestamps, MediaMTX logic, WebRTC player, YOLO, FastAPI.

---

## 7. CHANGES MADE (this session)

| Item | Change |
|------|--------|
| `scripts/aws_network_diagnostics.sh` | **Added** — read-only EC2 diagnostic script |
| `edge/network_ab_test.ps1` | **Added** — home/hotspot A/B test with debug logging |
| `docs/NETWORK_TEST_REPORT.md` | **Added/updated** — this report |

**No changes to:** ingest FFmpeg command, MediaMTX, WebRTC, HLS, Caddy, FastAPI, frontend, YOLO.

---

## 8. CHANGES NOT MADE

Confirmed **not modified:**

- `edge/ingest.py` FFmpeg pipeline
- MediaMTX configuration
- WebRTC / WebRTCPlayer
- HLS / Caddy routing
- FastAPI / frontend / YOLO / SageMaker
- SRT migration (deferred per test plan)

---

## 9. RECOMMENDED PRODUCTION ARCHITECTURE (smallest change)

**Phase A — Network only (no app changes):**

1. **AWS Console:** Remove temporary **TCP 8554** public ingress (if still present).
2. **AWS SG:** Add **inbound UDP 41641** to EC2.  
   *Why:* Tailscale WireGuard listens on UDP 41641; peers use dynamic source IPs for hole punching. Without this, EC2 cannot receive direct peer packets. This is Tailscale’s documented server requirement — not an application port.
3. **Windows router:** Enable UPnP **or** forward **UDP 41641 → 192.168.1.11**.
4. Re-test: `tailscale ping --until-direct 100.101.127.80` until **direct** (not DERP).
5. Re-run **existing** FFmpeg publisher — target **~1.0x speed, ~30 FPS**.

**Phase B — If Phase A insufficient:**

- Hotspot A/B (home router vs ISP NAT).
- Mumbai EC2 benchmark (network only, no prod migration yet).

**Phase C — Only if A+B fail:**

- Consider SRT or region move — not implemented yet.

**Security (parallel):**

- Rotate compromised `edge_publisher` credential (do not log new value).
- Remove/fix MediaMTX user `PS` (empty password).
- Keep 8554/8888/8889/9997 off public internet; use Caddy 80/443 for viewers.

---

## AWS actions checklist (manual)

- [ ] Remove SG rule: TCP 8554 from Windows public IP
- [ ] Add SG rule: UDP 41641 → EC2 (Tailscale direct)
- [ ] Run `scripts/aws_network_diagnostics.sh` on EC2
- [ ] Confirm `sudo tailscale ping --verbose 100.111.90.39` shows direct after fixes
- [ ] Re-measure FFmpeg publish speed/FPS without code changes
