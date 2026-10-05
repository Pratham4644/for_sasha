# Production Edge Ingestion Gateway

## Overview

In the unified platform, camera ingestion operates in **two modes**:

### Mode 1: Central Stream Supervisor (Default — Zero Edge Agent Required)
When your cameras and the platform backend are on the same local network or can be reached directly (e.g. `rtsp://192.168.1.11:8080/h264.sdp`), **no edge agent is required**.
- The backend's embedded `StreamSupervisor` (`production/backend/app/services/stream_manager.py`) automatically spawns FFmpeg processes to pull RTSP streams and publish to MediaMTX.
- AI pipelines (`production/backend/app/services/ai_pipeline.py`) are automatically attached to generate the annotated streams.

### Mode 2: Remote Edge Gateway (`ingest.py`)
When cameras reside behind an off-site private NAT / firewall (e.g. a remote branch, warehouse, or customer premise) where the central server cannot reach the camera's private IP:
1. Run `ingest.py` on an edge device (e.g., Raspberry Pi, mini PC, or local machine) on that network:
   ```bash
   python ingest.py "rtsp://camera_ip:554/stream" <media_path> <central_server_ip>
   ```
2. The edge script connects to the local camera via RTSP and pushes the stream directly to MediaMTX over authenticated RTSP TCP.
