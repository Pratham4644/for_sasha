# Security and Code Issues Audit

Audit date: 2026-10-07  
Scope: Remote-edge ingestion work + repository security review  
Note: Actual secret values are intentionally omitted from this document.

---

## CRITICAL

### 1. MediaMTX credentials committed in `mediamtx.yml`
- **Component:** `mediamtx.yml`
- **Problem:** Publish/read user password hashes are stored in the repository config file.
- **Impact:** Anyone with repo access can authenticate to MediaMTX publish/read paths.
- **Status:** NOT FIXED (out of scope for this task; requires coordinated rotation and deployment update)
- **Remediation:** Move credentials to environment/secrets manager; inject at deploy time; rotate all MediaMTX passwords.

### 2. RTSP publish port not reachable from edge without networking change
- **Component:** AWS Security Group / EC2 firewall
- **Problem:** Edge FFmpeg cannot publish to AWS MediaMTX when TCP 8554 is blocked from the edge egress IP.
- **Impact:** Zero active MediaMTX paths; all remote cameras remain offline.
- **Status:** NOT FIXED (requires manual AWS networking; code now documents and supports the flow)
- **Remediation:** Add inbound TCP 8554 restricted to edge public IP `/32`, or use VPN/WireGuard private connectivity.

### 3. Edge config API returns camera source URLs with embedded credentials
- **Component:** `backend/app/routes/edge.py`
- **Problem:** Authenticated edge gateway receives full RTSP URLs including camera credentials over HTTPS.
- **Impact:** Token compromise exposes all assigned camera credentials in one API response.
- **Status:** NOT FIXED (required for edge operation; matches prior Azure architecture)
- **Remediation:** Short-lived per-camera publish tokens, mTLS for edge agents, IP allowlisting, token rotation, separate credential endpoint with tighter scoping.

---

## HIGH

### 4. Backend previously pulled private LAN cameras from AWS
- **Component:** `backend/app/main.py`, `backend/app/routes/cameras.py`, `stream_manager.py`
- **Problem:** StreamManager always attempted FFmpeg ingest from AWS to `192.168.x.x` addresses.
- **Impact:** Guaranteed failure for remote LAN cameras; misleading CONNECTING/AI pipeline state.
- **Status:** FIXED
- **Remediation:** N/A — remote/private sources now use `remote_edge` mode and skip backend FFmpeg.

### 5. No edge orchestration existed
- **Component:** `edge/`
- **Problem:** Only standalone `ingest.py`; no `agent.py`, no backend assignment API.
- **Impact:** Manual per-camera ingest only; no reconciliation, restart, or assignment lifecycle.
- **Status:** FIXED
- **Remediation:** N/A — added `edge/agent.py` and `/api/v1/edge/config`.

### 6. WebSocket detection endpoint has no authentication
- **Component:** `backend/app/routes/websocket.py`
- **Problem:** `/api/ws/detections` accepts anonymous connections.
- **Impact:** Unauthorized clients can receive detection events.
- **Status:** NOT FIXED
- **Remediation:** Require JWT/cookie auth or scoped stream token on WebSocket connect.

### 7. MediaMTX Control API bound to `0.0.0.0:9997`
- **Component:** `mediamtx.yml`
- **Problem:** Control API listens on all interfaces.
- **Impact:** Path enumeration / control if port exposed publicly.
- **Status:** NOT FIXED
- **Remediation:** Bind to localhost only; access via SSH tunnel or private network.

### 8. Default dev secrets in `.env.example` and config defaults
- **Component:** `backend/app/config.py`, `.env.example`
- **Problem:** Development JWT secret, encryption key, and MediaMTX passwords documented as defaults.
- **Impact:** Production misconfiguration if defaults are reused.
- **Status:** NOT FIXED (production validator partially mitigates JWT/encryption key)
- **Remediation:** Remove defaults in production paths; fail startup if secrets unset.

---

## MEDIUM

### 9. `enable_camera` previously marked cameras ONLINE without publisher verification
- **Component:** `backend/app/routes/cameras.py`
- **Problem:** Enabled cameras could be marked ONLINE when FFmpeg spawn succeeded locally.
- **Impact:** False-positive online status.
- **Status:** FIXED (now sets CONNECTING; MediaMTX publisher required for ONLINE)
- **Remediation:** N/A

### 10. SSE detection stream not wired to broadcasts
- **Component:** `backend/app/routes/websocket.py`
- **Problem:** SSE endpoint sends heartbeats only.
- **Impact:** SSE fallback useless for live detections.
- **Status:** NOT FIXED
- **Remediation:** Subscribe SSE queue to `websocket_manager.broadcast`.

### 11. CORS allows credentials with configurable origins
- **Component:** `backend/app/main.py`, `FRONTEND_ORIGIN`
- **Problem:** Misconfigured origins could enable cross-site authenticated requests.
- **Impact:** Session abuse if origin list too broad.
- **Status:** NOT FIXED
- **Remediation:** Strict production origin list; no wildcards.

### 12. Camera connectivity test runs FFmpeg/ffprobe from backend
- **Component:** `stream_manager.test_camera_connectivity`
- **Problem:** Backend tests private URLs that it cannot reach in remote-edge deployments.
- **Impact:** Misleading diagnostics for LAN cameras tested from AWS UI.
- **Status:** NOT FIXED
- **Remediation:** Return guidance for remote-edge cameras; optionally proxy test via edge heartbeat.

### 13. Subprocess management duplicated across backend and edge
- **Component:** `stream_manager.py`, `edge/ingest.py`, `edge/agent.py`
- **Problem:** Separate FFmpeg lifecycle implementations.
- **Impact:** Behavioral drift, harder security review.
- **Status:** PARTIALLY ADDRESSED (edge ingest upgraded; backend unchanged by design)
- **Remediation:** Shared small process-supervisor utility if duplication grows.

---

## LOW

### 14. Minimal `ingest.py` lacked locks, stderr drain, stale PID cleanup
- **Component:** `edge/ingest.py`
- **Problem:** Previous version could leak FFmpeg processes and block on stderr pipes.
- **Impact:** Edge instability after crashes/restarts.
- **Status:** FIXED
- **Remediation:** N/A

### 15. `/streams` page not in sidebar
- **Component:** frontend navigation
- **Problem:** Hidden route.
- **Impact:** UX only.
- **Status:** NOT FIXED (explicitly out of scope)
- **Remediation:** Add nav link if desired.

### 16. `StatCard` component unused
- **Component:** `frontend/src/components/StatCard.tsx`
- **Problem:** Dead code.
- **Impact:** Maintenance noise only.
- **Status:** NOT FIXED
- **Remediation:** Remove or use in Dashboard.

---

## INFORMATIONAL

### 17. MongoDB credentials in environment only
- **Component:** deployment `.env`
- **Problem:** Standard secret-in-env pattern.
- **Impact:** Depends on host/file permissions.
- **Status:** NOT FIXED (expected pattern)
- **Remediation:** Use IAM/database user least privilege; restrict `.env` permissions.

### 18. SageMaker IAM permissions not reviewed in this task
- **Component:** AWS IAM / `sagemaker_client.py`
- **Problem:** Not audited here.
- **Impact:** Unknown over-permission risk.
- **Status:** NOT FIXED
- **Remediation:** Scope IAM policy to `sagemaker:InvokeEndpoint` on specific endpoint ARN.

### 19. AI pipeline starts before remote stream is available
- **Component:** `ai_pipeline.py`, ingestion service
- **Problem:** AI workers run with zero inferences until edge publishes.
- **Impact:** Expected idle state; not a security issue.
- **Status:** NOT FIXED (by design)
- **Remediation:** Optional deferred AI start when `remote_edge` and path offline.

### 20. Debug instrumentation added for remote-edge verification
- **Component:** `backend/app/services/ingestion.py`, `backend/app/routes/edge.py`, `edge/agent.py`, `edge/ingest.py`
- **Problem:** Temporary NDJSON debug logs write to `debug-abbe6f.log`.
- **Impact:** Low; no secrets logged by design.
- **Status:** NOT FIXED (intentional for verification session)
- **Remediation:** Remove `# region agent log` blocks after production verification.

---

## Summary of fixes in this task

| Issue | Fix |
|-------|-----|
| AWS StreamManager pulling LAN cameras | `ingestion_mode` + auto private-IP detection |
| Missing edge orchestration | `edge/agent.py` + `/api/v1/edge/config` |
| Weak edge ingest worker | Production-grade `edge/ingest.py` |
| False online status on enable | CONNECTING until MediaMTX publisher verified |
| No remote-edge status sync | `edge_status.py` background loop |
