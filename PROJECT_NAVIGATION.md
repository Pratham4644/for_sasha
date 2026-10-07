# PROJECT NAVIGATION — Dynamic Remote Camera & AI Platform (StreamOps)

> **Purpose:** Token-efficient map of the entire codebase. Read this file first before exploring source files.
> **Last mapped:** 2026-10-07 | **Repo root:** `production/`

---

## 1. What This Project Is

Multi-tenant **remote camera streaming + AI detection** platform:

| Layer | Tech |
|-------|------|
| Frontend | React 18, TypeScript, Vite, Tailwind, React Router |
| Backend | FastAPI, MongoDB (Motor async), JWT + HttpOnly cookies |
| Streaming | FFmpeg → MediaMTX (RTSP/HLS/WebRTC/WHEP) |
| AI | AWS SageMaker YOLO endpoint + local Ultralytics fallback |
| Deploy | Docker Compose (mediamtx + backend + frontend/nginx) |

**Product UI name:** StreamOps

---

## 2. Architecture (End-to-End)

```
Camera RTSP/HTTP
    │
    ├─[Mode 1: Central]──► stream_manager.py (FFmpeg per camera)
    │                           │
    └─[Mode 2: Edge]────► edge/ingest.py ──► MediaMTX /{media_path}
                                    │
                                    ▼
                         ai_pipeline.py (OpenCV + SageMaker/local YOLO)
                                    │
                                    ▼
                         FFmpeg publish → MediaMTX /{media_path}-ai
                                    │
                                    ▼
                         Frontend WebRTCPlayer (WHEP/HLS)
                                    │
                         Detection events → MongoDB → WS /api/ws/detections
```

**Startup sequence** (`backend/app/main.py` lifespan):
1. Register stream status → MongoDB callback
2. Connect MongoDB, ensure indexes
3. Auto-start enabled cameras (FFmpeg + AI)
4. Start retention cleanup loop
5. Shutdown: stop streams/AI, close DB

---

## 3. Directory Map

```
production/
├── .env / .env.example          # All config (copy example → .env)
├── docker-compose.yml           # mediamtx + backend + frontend
├── mediamtx.yml                 # MediaMTX paths/auth config
├── Caddyfile                    # Optional TLS reverse proxy
├── run_backend.py               # Local backend entry (uvicorn)
├── run_mediamtx.py              # Local MediaMTX launcher
├── start_all.ps1 / .bat         # Windows: launch all 3 services
├── openapi.json                 # Generated API spec
│
├── backend/
│   ├── Dockerfile               # Python 3.13 + FFmpeg
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # ★ FastAPI app, lifespan, CORS
│   │   ├── config.py            # ★ Settings from .env
│   │   ├── models.py            # ★ Domain models (Pydantic)
│   │   ├── schemas.py           # API request/response DTOs
│   │   ├── auth.py              # JWT, bcrypt, cookies, Fernet creds
│   │   ├── permissions.py       # RBAC matrix + tenant filter
│   │   ├── db.py                # MongoDB async client + indexes
│   │   ├── websocket_manager.py # WS connection pool + broadcast
│   │   ├── middleware/
│   │   │   ├── request_id.py    # X-Request-ID
│   │   │   └── error_handler.py # Standard JSON errors
│   │   ├── routes/              # ★ All HTTP/WS endpoints
│   │   └── services/            # ★ Business logic
│   └── tests/                   # pytest (auth, cameras, detections, health, stream_manager)
│
├── frontend/
│   ├── Dockerfile + nginx.conf  # Multi-stage build → nginx :80
│   ├── vite.config.ts           # Dev proxy /api → :8000
│   ├── package.json
│   └── src/
│       ├── App.tsx              # ★ Routes
│       ├── services/api.ts      # ★ Fetch API client
│       ├── types/index.ts       # ★ All TS interfaces
│       ├── context/             # AuthContext, DetectionSocketContext
│       ├── layouts/AppLayout.tsx
│       ├── components/          # Sidebar, Navbar, WebRTCPlayer, StatusBadge
│       └── pages/               # 13 page components
│
├── edge/
│   ├── ingest.py                # Remote NAT edge RTSP → MediaMTX push
│   └── README.md
│
├── scripts/                     # Ops & dev utilities
│   ├── seed_admin.py            # Create default admin user
│   ├── check_status.py          # Platform health check
│   ├── e2e_verification.py      # End-to-end test
│   ├── multi_camera_acceptance_test.py
│   └── start_test_stream.py     # Fake RTSP for testing
│
└── scratch/                     # Ad-hoc DB/analytics debug scripts (not prod)
```

---

## 4. Quick Lookup — "Where Do I Change X?"

| Task | Go to |
|------|-------|
| Add API endpoint | `backend/app/routes/*.py` → register in `routes/__init__.py` |
| Change auth/JWT | `backend/app/auth.py` |
| Role permissions | `backend/app/permissions.py` → `ROLE_PERMISSIONS` |
| DB schema/indexes | `backend/app/models.py` + `backend/app/db.py` |
| Camera stream lifecycle | `backend/app/services/stream_manager.py` |
| MediaMTX path provisioning | `backend/app/services/mediamtx.py` |
| AI inference + overlay | `backend/app/services/ai_pipeline.py` |
| SageMaker/local YOLO | `backend/app/services/sagemaker_client.py` |
| Detection retention TTL | `backend/app/services/retention.py` + `DETECTION_RETENTION_DAYS` |
| WebSocket broadcast | `backend/app/websocket_manager.py` + `routes/websocket.py` |
| Add frontend page | `frontend/src/pages/` → route in `App.tsx` → nav in `Sidebar.tsx` |
| API calls from UI | `frontend/src/services/api.ts` |
| TypeScript types | `frontend/src/types/index.ts` |
| Live video player | `frontend/src/components/WebRTCPlayer.tsx` |
| Real-time detection toasts | `frontend/src/context/DetectionSocketContext.tsx` |
| RBAC in UI | `frontend/src/context/AuthContext.tsx` → `hasPermission()` |
| Env vars | `.env` / `backend/app/config.py` |
| Docker deploy | `docker-compose.yml` + per-service Dockerfiles |
| Remote camera behind NAT | `edge/ingest.py` |

---

## 5. Backend — File Reference

### Core (`backend/app/`)

| File | Key exports | Responsibility |
|------|-------------|----------------|
| `main.py` | `app`, `lifespan` | FastAPI factory, auto-start cameras, middleware |
| `config.py` | `Settings`, `settings` | Pydantic settings from `.env` |
| `models.py` | `User`, `Organization`, `Site`, `Camera`, `DetectionEvent`, `AuditLog`, `UserRole`, `CameraStatus` | Domain models |
| `schemas.py` | `ApiResponse[T]`, `CameraCreate`, `DetectionEventCreate`, etc. | API DTOs |
| `auth.py` | `get_current_user`, `create_access_token`, `hash_password`, `encrypt_camera_credentials` | Auth deps |
| `permissions.py` | `require_permission`, `require_role`, `get_tenant_filter`, `ROLE_PERMISSIONS` | RBAC |
| `db.py` | `db`, `Database` | Collections: users, cameras, detection_events, sites, organizations, logs |
| `websocket_manager.py` | `websocket_manager`, `WebSocketManager` | Broadcast to all WS clients |

### Routes (`backend/app/routes/`)

| File | Prefix | Notes |
|------|--------|-------|
| `auth.py` | `/auth` | register, login, logout, me, profile |
| `cameras.py` | `/cameras` | CRUD, start/stop/restart, status, playback, test |
| `detections.py` | `/detections`, `/detection-events`, `/detection-logs` | Query, ingest, CSV export |
| `analytics.py` | `/analytics` | Dashboard aggregations |
| `organizations.py` | `/organizations` | Org CRUD (SUPER_ADMIN list all) |
| `sites.py` | `/sites` | Site CRUD |
| `users.py` | `/users` | User CRUD |
| `logs.py` | `/logs`, `/audit-logs` | Audit log read + `record_audit_log()` helper |
| `health.py` | `/health`, `/system/status` | Health probes + telemetry |
| `websocket.py` | `/ws/detections`, `/detections/stream` | WS + SSE (SSE not wired to broadcast) |
| `__init__.py` | — | Mounts all under `/api` AND `/api/v1` |

### Services (`backend/app/services/`)

| File | Key class | Responsibility |
|------|-----------|----------------|
| `stream_manager.py` | `StreamManager`, `stream_manager` | FFmpeg per-camera, reconnect, status callback |
| `mediamtx.py` | `MediaMTXService`, `mediamtx_service` | Control API, URL generation, path CRUD |
| `ai_pipeline.py` | `AIPipelineManager`, `ai_pipeline_manager` | RTSP read → infer → overlay → publish `-ai` stream |
| `sagemaker_client.py` | `SageMakerInferenceClient` | boto3 invoke + local YOLO fallback |
| `camera.py` | helpers | URL sanitize, credential decrypt, playback format |
| `retention.py` | `retention_cleanup_loop` | Background TTL cleanup |

---

## 6. API Endpoint Index

> All routes exist at **both** `/api/...` and `/api/v1/...` unless noted.

### Auth — `/auth`
| Method | Path | Auth |
|--------|------|------|
| POST | `/register` | None |
| POST | `/login` | None |
| POST | `/logout` | None |
| GET | `/me` | Required |
| PATCH | `/profile` | Required |

### Cameras — `/cameras`
| Method | Path | Permission |
|--------|------|------------|
| POST | `` | `camera:create` |
| GET | `` | `camera:read` |
| GET | `/{id}` | `camera:read` |
| PUT/PATCH | `/{id}` | `camera:update` |
| DELETE | `/{id}` | `camera:delete` |
| POST | `/{id}/start\|stop\|restart` | `stream:control` |
| POST | `/{id}/enable\|disable` | `camera:update` |
| GET | `/{id}/status\|stream\|playback` | read |
| POST | `/{id}/test` | `camera:read` |
| POST | `/test-source` | `camera:create` |

### Detections
| Method | Path |
|--------|------|
| GET | `/detections`, `/detection-logs` |
| GET | `/detections/{id}` |
| GET | `/cameras/{id}/detections`, `.../latest` |
| POST | `/detection-events` |
| GET | `/detection-logs/export` (CSV, max 5000) |

### Other
| Method | Path | Notes |
|--------|------|-------|
| GET | `/analytics` | Dashboard data |
| GET/PATCH | `/organizations/current`, `/{id}` | |
| GET | `/organizations` | SUPER_ADMIN only |
| CRUD | `/sites`, `/users` | |
| GET | `/logs`, `/audit-logs` | |
| GET | `/health`, `/healthz`, `/health/public`, `/health/database`, `/health/mediamtx`, `/health/ai` | No auth |
| GET | `/system/status` | Full telemetry |
| WS | `/ws/detections` | No auth; ping/pong + detection_event broadcast |
| GET | `/` | Service metadata |

---

## 7. Database Model Relationships

```
Organization (1) ──< User, Site, Camera, DetectionEvent, AuditLog
Site (1) ──< Camera
Camera (1) ──< DetectionEvent
```

**Collections:** `users`, `organizations`, `sites`, `cameras`, `detection_events`, `logs`

**Tenant isolation:** All queries filtered by `organization_id` except `SUPER_ADMIN`.

**Key indexes** (`db.ensure_indexes()`): unique email, camera `(org_id, media_path)`, detection TTL on `expires_at`.

---

## 8. Auth & RBAC

### Flow
1. Login/register → bcrypt + JWT (`sub`, `email`, `org`, `role`)
2. Token via HttpOnly cookie (`camera_session`) + JSON `token` field
3. Protected routes: cookie first, then `Authorization: Bearer`
4. `get_current_user()` → load from MongoDB → check `is_active`

### Roles (hierarchy)
| Role | Scope |
|------|-------|
| `SUPER_ADMIN` | Cross-tenant, all permissions |
| `ORG_ADMIN` | Full org management |
| `OPERATOR` | Read + camera update + stream control + detection create |
| `VIEWER` | Read-only |

Permissions defined in `permissions.py` → `ROLE_PERMISSIONS` dict. Pattern: `resource:action` (e.g. `camera:create`, `stream:control`, `analytics:read`).

Camera RTSP credentials stored encrypted in `credentials_ref` (Fernet via `CAMERA_ENCRYPTION_KEY`). Never returned in API responses.

---

## 9. WebSocket Events

**Endpoint:** `WS /api/ws/detections` (also `/ws/detections`)

| Direction | Message |
|-----------|---------|
| Client → Server | `{"type": "ping"}` |
| Server → Client | `{"type": "pong"}` |
| Server → Client | `{"type": "detection_event", "data": {...}}` |

**Emitted by:** `ai_pipeline.py` (auto) and `POST /detection-events` (manual).

**Frontend consumer:** `DetectionSocketContext.tsx` — toasts + `recentDetections` buffer (max 50).

---

## 10. Frontend — File Reference

### Entry & routing
| File | Role |
|------|------|
| `main.tsx` | ReactDOM mount |
| `App.tsx` | Router, AuthProvider, DetectionSocketProvider |
| `layouts/AppLayout.tsx` | Auth guard, Sidebar + Navbar shell |

### Pages (`frontend/src/pages/`)
| File | Route | Purpose |
|------|-------|---------|
| `Login.tsx` | `/login` | Auth |
| `Register.tsx` | `/register` | Org + admin signup |
| `Dashboard.tsx` | `/dashboard` | Analytics KPIs, trends, health |
| `Cameras.tsx` | `/cameras` | Camera list + CRUD modal |
| `CameraDetail.tsx` | `/cameras/:id`, `/streams/cameras/:id` | Live player, AI toggle, detections |
| `Sites.tsx` | `/sites` | Site grid |
| `SiteDetail.tsx` | `/sites/:id` | Site cameras |
| `Streams.tsx` | `/streams` | Multi-camera wall (NOT in sidebar) |
| `Logs.tsx` | `/logs` | Detection + audit logs |
| `Users.tsx` | `/users` | User admin (admin only) |
| `Health.tsx` | `/health` | System health (30s refresh) |
| `Settings.tsx` | `/settings` | Org profile |
| `Profile.tsx` | `/profile` | Name/password |

### Components
| File | Role |
|------|------|
| `WebRTCPlayer.tsx` | HLS default, WebRTC WHEP fallback, reconnect, fullscreen |
| `Sidebar.tsx` | Nav (Users hidden for non-admin) |
| `Navbar.tsx` | Org badge, logout |
| `StatusBadge.tsx` | ONLINE/OFFLINE/DEGRADED pills |
| `StatCard.tsx` | KPI card (unused — Dashboard inlines cards) |

### State
| File | State |
|------|-------|
| `AuthContext.tsx` | `user`, `organization`, `hasRole()`, `hasPermission()` |
| `DetectionSocketContext.tsx` | `latestDetection`, `recentDetections`, toasts |
| Pages | Local `useState` + `useEffect` (no Redux/React Query) |

### API client (`services/api.ts`)
- Singleton: `export const api = new ApiClient()`
- Base: `/api/v1` (override: `VITE_API_BASE_URL`)
- Auth: `credentials: 'include'`
- Unwraps `{ success, data }` wrapper

---

## 11. Environment Variables (Grouped)

See `.env.example` for full list. Critical ones:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MONGODB_URI` | `mongodb://127.0.0.1:27017` | Database |
| `JWT_SECRET` | dev default | Must change in production (≥32 chars) |
| `CAMERA_ENCRYPTION_KEY` | dev default | Fernet key for camera creds |
| `MEDIAMTX_*` | localhost ports | Streaming server |
| `PUBLIC_WEBRTC_URL` / `PUBLIC_HLS_URL` | localhost | Browser playback URLs |
| `FFMPEG_ENCODER` | `libx264` | Also: `h264_nvenc`, `h264_amf`, `copy` |
| `AI_ENABLED` | `true` | Toggle AI pipeline |
| `SAGEMAKER_ENDPOINT_NAME` | `yolo26s-cctv-endpoint` | AWS endpoint |
| `DETECTION_RETENTION_DAYS` | `30` | MongoDB TTL |
| `FRONTEND_ORIGIN` | localhost:5173 | CORS |

**Production validation:** Non-default JWT + encryption key; `COOKIE_SECURE=true`.

---

## 12. How to Run

### Windows (all services)
```powershell
.\start_all.ps1
# Frontend: http://localhost:5173
# API docs:  http://127.0.0.1:8000/docs
# Default:   admin@platform.local / adminpassword123
```

### Manual
```bash
python run_mediamtx.py          # Terminal 1
python run_backend.py           # Terminal 2
cd frontend && npm run dev      # Terminal 3
```

### Docker
```bash
docker compose up --build
# Frontend: http://localhost:80
# Backend:  http://localhost:8000
```

### Tests
```bash
cd backend && pytest
```

### Seed admin
```bash
python scripts/seed_admin.py
```

---

## 13. External Integrations

| Service | Config | Used in |
|---------|--------|---------|
| **MediaMTX** | `MEDIAMTX_API_URL`, ports 8554/8888/8889/9997 | `mediamtx.py`, FFmpeg publish |
| **FFmpeg** | `FFMPEG_BINARY`, `FFMPEG_ENCODER` | `stream_manager.py`, `ai_pipeline.py` |
| **AWS SageMaker** | `SAGEMAKER_*`, AWS creds | `sagemaker_client.py` |
| **Local YOLO** | Ultralytics fallback | `sagemaker_client.py` when SageMaker unavailable |
| **MongoDB** | `MONGODB_URI` | `db.py` |
| **OpenCV** | — | `ai_pipeline.py` frame capture + overlay |

---

## 14. Test Coverage Map

| Area | File | Covered? |
|------|------|----------|
| Auth flow | `tests/test_auth.py` | ✅ |
| Camera CRUD | `tests/test_cameras.py` | ✅ |
| Detections | `tests/test_detections.py` | ✅ |
| Health | `tests/test_health.py` | ✅ |
| Stream manager units | `tests/test_stream_manager.py` | ✅ |
| WebSocket/SSE | — | ❌ |
| Analytics | — | ❌ |
| Users/Sites/Orgs | — | ❌ |
| AI pipeline | — | ❌ |
| MediaMTX integration | — | ❌ (mocked/absent) |

**Test infra:** `conftest.py` — mongomock DB, seeded SUPER_ADMIN, `TestClient`.

---

## 15. Known Gaps / Notes

- `/streams` page exists but is **not in Sidebar** — direct URL only
- SSE `/detections/stream` sends heartbeats only; not wired to detection broadcast
- WebSocket has **no auth** on connect
- `StatCard.tsx` component exists but Dashboard inlines its own KPI cards
- `scratch/` contains ad-hoc debug scripts — not part of production runtime
- Routes mounted at both `/api` and `/api/v1` for backward compatibility

---

## 16. Common Debug Paths

| Symptom | Check |
|---------|-------|
| Camera stays OFFLINE | `stream_manager.py` logs, MediaMTX publisher status, `GET /cameras/{id}/status` |
| No AI overlay stream | `ai_pipeline.py`, `GET /health/ai`, SageMaker creds |
| Playback fails in browser | `PUBLIC_WEBRTC_URL`, nginx `/webrtc/` proxy, MediaMTX read creds |
| Auth 401 | Cookie domain, CORS `FRONTEND_ORIGIN`, JWT expiry |
| Detections not live | WS connection in browser devtools, `websocket_manager.py` |
| DB errors | `MONGODB_URI`, indexes in `db.py` |

---

## 17. Git History (Recent)

```
e8c9a7e Sync complete production project
68d564c Restore frontend API and domain types
02af633 Add secure gitignore
ada4562 Update complete system
b153206 checkpoint: current working state
a32a207 Rebuild camera platform with dynamic architecture
```

---

*Use section 4 ("Where Do I Change X?") for fastest navigation. For deep dives, jump directly to the ★ marked files.*
