# Remote Edge Gateway

## Architecture

```
Private Camera LAN (192.168.x.x)
        |
        v
Windows / Pi Edge Machine (edge/agent.py)
        |
        +--> one ingest.py worker per assigned camera
        |
        +--> one FFmpeg process per ingest worker
        |
        | outbound RTSP/TCP (restricted AWS SG rule)
        v
AWS MediaMTX :8554
        |
        v
Caddy /hls + /webrtc -> Frontend
```

## Two ingestion modes

| Mode | When to use | Who pulls the camera |
|------|-------------|----------------------|
| `local` | Camera reachable from AWS backend | Backend `StreamManager` |
| `remote_edge` | Camera on private LAN / customer site | Edge gateway `ingest.py` |

Cameras with private source URLs (`192.168.x.x`, `10.x.x.x`, etc.) are automatically treated as `remote_edge` even if the field is not set yet.

The AWS backend must **not** attempt to FFmpeg-pull private LAN cameras directly.

## Setup

### 1. AWS backend

Add to backend `.env`:

```env
EDGE_GATEWAY_TOKEN=<generate-a-long-random-token>
EDGE_GATEWAY_ORG_ID=<your-organization-id>
MEDIAMTX_PUBLISH_HOST=<aws-public-ip-or-hostname>
```

Run once on AWS:

```bash
python scripts/seed_edge_gateway.py
```

Deploy/restart the backend after setting the token.

### 2. AWS networking (manual, required)

The edge machine must reach MediaMTX RTSP publish port on AWS.

**Do not** open RTSP `8554` to `0.0.0.0/0`.

Minimum secure option:

1. Discover the edge machine public egress IP.
2. AWS Security Group inbound rule:
   - Protocol: TCP
   - Port: `8554`
   - Source: `<edge-public-ip>/32`
3. Confirm MediaMTX listens on the host interface used by AWS (native install on EC2).

Alternative: site-to-site VPN / WireGuard between edge LAN and AWS VPC.

### 3. Edge machine (192.168.1.12)

```powershell
cd edge
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env with EDGE_API_URL, EDGE_GATEWAY_TOKEN, MEDIAMTX_HOST, MEDIAMTX_PUBLISH_PASSWORD
python agent.py
```

`EDGE_API_URL` should point at your Caddy HTTPS domain:

```env
EDGE_API_URL=https://your-domain.example/api/v1/edge/config
```

### 4. Verify

1. Edge agent log: `Received N assigned camera(s)`
2. AWS MediaMTX API: `/v3/paths/list` shows `cam_*` paths
3. Frontend HLS: `/hls/cam_*/index.m3u8`
4. Backend health: online cameras > 0

## Standalone ingest (debug)

```powershell
$env:EDGE_CAMERA_ID="test_cam"
$env:EDGE_SOURCE_URL="rtsp://192.168.1.11:8080/h264.sdp"
$env:EDGE_MEDIA_PATH="test_cam"
$env:MEDIAMTX_HOST="<aws-public-ip>"
$env:MEDIAMTX_RTSP_PORT="8554"
$env:MEDIAMTX_PUBLISH_USERNAME="edge_publisher"
$env:MEDIAMTX_PUBLISH_PASSWORD="<from-backend-env>"
python ingest.py
```

If FFmpeg starts but no MediaMTX path appears, the publish TCP connection is blocked (Security Group / firewall).

## API

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /api/v1/edge/config` | `Bearer EDGE_GATEWAY_TOKEN` | Assigned cameras + publish host |
| `POST /api/v1/edge/heartbeat` | same | Optional gateway heartbeat |
