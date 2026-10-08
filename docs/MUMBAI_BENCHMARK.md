# Mumbai vs Sydney Region Benchmark

**Purpose:** Determine whether moving MediaMTX ingest target closer to the India edge restores ~1.0x FFmpeg / ~30 FPS **without** changing the streaming pipeline.

**Status:** Sydney baseline complete. Mumbai node not yet provisioned.

---

## Sydney baseline (confirmed 2026-10-08)

| Metric | Value |
|--------|-------|
| Tailscale | Direct `3.26.96.100:41641` |
| RTT | ~331 ms |
| FFmpeg speed | **0.111x** |
| Publish FPS | **2.56** |
| Frames / 30 s | 77 |
| Video time / 30 s wall | 2.82 s |

---

## Mumbai setup (one-time)

### 1. AWS Console

- Launch **Ubuntu 22.04/24.04** in **ap-south-1** (Mumbai), `t3.small` is sufficient.
- Security Group:
  - **Inbound UDP 41641** from `0.0.0.0/0` (Tailscale WireGuard)
  - **Do not** expose 8554/8888/8889/9997 publicly
- SSH in, then:

```bash
git clone https://github.com/Pratham4644/for_sasha.git ~/camera-platform
cd ~/camera-platform
git pull origin main
bash scripts/mumbai_benchmark_setup.sh
sudo tailscale up   # same tailnet as Sydney + Windows
tailscale ip -4     # note Mumbai Tailscale IP
```

### 2. Windows edge — run identical publish test

```powershell
cd C:\path\to\production

# Sydney (baseline — expect ~0.11x / ~2.5 FPS)
powershell -ExecutionPolicy Bypass -File edge/benchmark_region_publish.ps1 -Label sydney -MtxHost 100.101.127.80

# Mumbai (replace with Mumbai Tailscale IP from step 1)
powershell -ExecutionPolicy Bypass -File edge/benchmark_region_publish.ps1 -Label mumbai -MtxHost <MUMBAI_TS_IP>
```

Both tests use the **same FFmpeg flags as `ingest.py`** (H.264 copy, RTSP/TCP, no wallclock timestamps).

### 3. Interpret results

| Mumbai result | Action |
|---------------|--------|
| ~1.0x / ~30 FPS | **Region migration** to `ap-south-1` is the production fix; keep architecture |
| Still ~0.1x | Report evidence; evaluate SRT (do not implement until benchmark complete) |

Results append to `debug-abbe6f.log` with `hypothesisId: H12`.

---

## Security notes

- Tear down Mumbai test EC2 after benchmark.
- Rotate `edge_publisher` if credentials were exposed in logs.
- Remove temporary public TCP 8554 SG rule on Sydney if still present.
