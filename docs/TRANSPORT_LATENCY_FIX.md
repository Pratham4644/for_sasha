# Transport Latency Root Cause & Fix

## Diagnosis (2026-10-08, measured from Windows edge 100.111.90.39)

### Root cause

**RTSP/TCP video publish is collapsing on the India → AWS Sydney WAN path** due to high RTT (~320–500 ms), severe TCP reordering (`rcv_ooopack` thousands), and effective throughput ~25–31 kbps (`delivery_rate` from `ss -tin`). FFmpeg is blocked waiting for TCP ACKs while sending H.264 to MediaMTX.

This is a **network transport pathology**, not camera, timestamp, MediaMTX signaling, WebRTC, YOLO, or frontend rendering.

### Contributing causes

1. **Geographic distance (primary after Fix 1)** — India → AWS Sydney direct Tailscale RTT ~317–387 ms; RTSP/TCP cannot sustain real-time H.264 at this latency.
2. **Tailscale DERP relay (fixed 2026-10-08)** — was ~400–500 ms RTT; now direct `3.26.96.100:41641`. **Did not restore ~1.0x FFmpeg speed** (still ~0.10x).
3. **Windows router had no UPnP/NAT-PMP** — resolved with UDP 41641 forward / AWS SG fix for direct peer.
4. **Public EC2 path also unhealthy** — ~320 ms RTT, severe TCP reordering (~0.12x FFmpeg on public IP).

### NOT the root cause

| Layer | Status |
|-------|--------|
| Camera RTSP | ~30 FPS verified |
| FFmpeg input | ~299 frames / 10 s |
| Timestamps | Fixed (do **not** re-add `-use_wallclock_as_timestamps 1`) |
| muxdelay / flush_packets | Ruled out by minimal publisher test |
| MediaMTX | Receives what arrives; reader slow because input is slow |
| WebRTC / HLS / Caddy | Presentation works; starved by upstream throughput |
| YOLO / AI | Downstream of transport bottleneck |

---

## Safest fix (in priority order)

### Fix 1 — Establish Tailscale direct connection (required first)

**AWS EC2 Security Group** — add inbound:

| Protocol | Port | Source | Purpose |
|----------|------|--------|---------|
| UDP | 41641 | 0.0.0.0/0 | Tailscale WireGuard direct peer |

Do **not** expose 8554/8888/8889/9997 publicly for production viewing.

**AWS EC2** — verify Tailscale allows direct:

```bash
sudo tailscale status
sudo tailscale ping --until-direct 100.111.90.39
tailscale netcheck
```

**Windows edge** — firewall already allows Tailscale inbound (verified). Fix **router NAT**:

- Enable UPnP on router, **or**
- Forward **UDP 41641** → `192.168.1.11` (Windows edge)

**Validation:**

```powershell
tailscale ping --until-direct 100.101.127.80
```

Success = `via 100.x.x.x:41641` (direct), RTT should drop well below 400 ms.

**A/B test:** Repeat on phone hotspot. If direct works on hotspot but not home ISP → router/ISP NAT is the blocker.

### Fix 2 — Region placement benchmark (if Fix 1 insufficient)

India → Sydney will remain ~150–250 ms even with direct WireGuard. RTSP/TCP may still struggle.

Before migrating production, benchmark identical FFmpeg publish test against:

- Current: `ap-southeast-2` (Sydney) `100.101.127.80:8554`
- Trial: `ap-south-1` (Mumbai) EC2 + Tailscale

Target: FFmpeg `speed= ~1.0x`, publish ~30 FPS, reader ~30 FPS.

### Fix 3 — Protocol change (only if Fix 1 + 2 fail)

If TCP throughput remains <0.5x after direct Tailscale + optimal region, RTSP/TCP is unsuitable for this path. Evaluate **SRT** or **RTSP/UDP** ingest (MediaMTX config change + ingest output change). Do not implement until measured.

---

## Application code status

`edge/ingest.py` FFmpeg command is correct for stream-copy:

- **Does not** include `-use_wallclock_as_timestamps 1` (confirmed)
- Uses `-c:v copy`, `-muxdelay 0`, `-flush_packets 1`

**No application rewrite required** until network path is fixed.

Run diagnostics:

```powershell
cd edge
python transport_diagnostics.py
```

---

## Security reminders

- [ ] Remove temporary SG rule: TCP 8554 from Windows public IP
- [ ] Rotate compromised `edge_publisher` MediaMTX credential
- [ ] Remove or secure MediaMTX user `PS` (empty password)

---

## Success criteria (concrete numbers)

| Metric | Current (broken) | Target |
|--------|------------------|--------|
| Tailscale path | DERP ~400 ms | Direct, RTT <150 ms (ideal) |
| FFmpeg publish speed | ~0.05–0.12x | ≥0.95x |
| Publish FPS | ~1–3 FPS | ~30 FPS |
| MediaMTX reader FPS | ~2–4 FPS | ~30 FPS |
| `ss delivery_rate` | ~25 kbps | ≥2 Mbps for 720p H.264 |
| `rcv_ooopack` | thousands | minimal |
