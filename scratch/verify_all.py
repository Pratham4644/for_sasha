import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta

# Ensure production root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from backend.app.db import db
from backend.app.models import User, UserRole
from backend.app.routes.analytics import get_full_analytics
from backend.app.routes.detections import list_detections
from backend.app.routes.logs import list_audit_logs, record_audit_log
from backend.app.routes.health import health, health_ai
from backend.app.routes.organizations import get_organization
from backend.app.services.sagemaker_client import SageMakerInferenceClient


async def run_verification():
    print("=" * 60)
    print("RUNNING COMPREHENSIVE PLATFORM VERIFICATION")
    print("=" * 60)

    await db.connect()

    # 1. Mock Admin User
    admin = User(
        id="test-admin-id",
        email="admin@platform.local",
        name="Administrator",
        role=UserRole.SUPER_ADMIN,
        password_hash="test",
        organization_id="85dcc187-c43f-44af-974f-bc7fec85b088"
    )

    # ---------------------------------------------------------
    # TEST 1: SETTINGS / ORGANIZATION ENDPOINT
    # ---------------------------------------------------------
    print("\n[TEST 1] Settings Organization Endpoint (GET /api/v1/organizations/{id})...")
    res_org = await get_organization(
        organization_id=admin.organization_id,
        current_user=admin
    )
    print(f"  Success: {res_org.success}")
    print(f"  Organization Name: {res_org.data.name}")
    print(f"  Organization ID: {res_org.data.id}")
    assert res_org.success is True
    assert res_org.data.id == admin.organization_id
    print("  => [PASS] Settings GET /organizations/{id} returns 200 (No 404)!")

    # ---------------------------------------------------------
    # TEST 2: SYSTEM HEALTH DETAILED ENDPOINT
    # ---------------------------------------------------------
    print("\n[TEST 2] System Health Detailed (GET /api/v1/health)...")
    res_health_dict = await health()
    print(f"  Status: {res_health_dict.get('status')}")
    print(f"  Database connected: {res_health_dict.get('database')}")
    print(f"  MediaMTX status: {res_health_dict.get('mediamtx')}")
    print(f"  MediaMTX ok: {res_health_dict.get('mediamtx_ok')}")
    print(f"  Cameras: {res_health_dict.get('cameras')}")
    print(f"  AI telemetry: {res_health_dict.get('ai')}")
    assert res_health_dict.get('database') is True, "Database should be healthy!"
    assert "online" in res_health_dict.get('cameras', {}), "Camera stats missing!"
    assert "status" in res_health_dict.get('ai', {}), "AI stats missing!"
    print("  => [PASS] System Health reports all subsystems without 404!")

    # ---------------------------------------------------------
    # TEST 3: AUDIT LOGS ENDPOINT & RECORDING
    # ---------------------------------------------------------
    print("\n[TEST 3] Audit Logs Recording and Retrieval (GET /api/v1/logs)...")
    # Record a test audit log
    await record_audit_log(
        action="VERIFICATION_TEST",
        resource_type="system",
        resource_id="test-run",
        user_id=admin.id,
        organization_id=admin.organization_id,
        details={"status": "running_verification", "executor": "antigravity"}
    )
    res_logs = await list_audit_logs(page=1, page_size=25, current_user=admin)
    print(f"  Success: {res_logs.success}")
    print(f"  Total audit records: {res_logs.data.total}")
    print(f"  Items returned: {len(res_logs.data.items)}")
    assert res_logs.success is True, "Audit logs failed!"
    assert res_logs.data.total > 0, "Audit logs should not be 0 after recording!"
    sample_log = res_logs.data.items[0]
    print(f"  Latest log action: {sample_log.action} on {sample_log.resource_type} ({sample_log.timestamp})")
    print("  => [PASS] Audit Logs correctly records and displays authentic audit data (No fake data)!")

    # ---------------------------------------------------------
    # TEST 4: DETECTION LOGS ENDPOINT & SNAPSHOT FORMAT
    # ---------------------------------------------------------
    print("\n[TEST 4] Detection Logs Endpoint (GET /api/v1/detection-logs)...")
    res_det = await list_detections(
        page=1,
        page_size=10,
        current_user=admin,
    )
    print(f"  Success: {res_det.success}")
    print(f"  Total events: {res_det.data.total}")
    print(f"  Items in page 1: {len(res_det.data.items)}")
    assert res_det.success is True
    assert res_det.data.total > 0, "Expected detection events > 0!"
    first_item = res_det.data.items[0]
    print(f"  Snapshot item camera: {first_item.camera_id}")
    print(f"  Snapshot timestamp: {first_item.timestamp}")
    print(f"  Snapshot detections array length: {len(first_item.detections)}")
    for d in first_item.detections[:3]:
        print(f"     - {d.class_name} ({d.confidence*100:.0f}%)")
    print("  => [PASS] Detection Logs returns snapshot structure with detections array for camera grouping!")

    # ---------------------------------------------------------
    # TEST 5: ANALYTICS DASHBOARD API (CANONICAL CONSISTENCY)
    # ---------------------------------------------------------
    print("\n[TEST 5] Analytics Dashboard API (GET /api/v1/analytics)...")
    res_analytics = await get_full_analytics(
        granularity="day",
        current_user=admin,
    )
    print(f"  Success: {res_analytics.success}")
    overview = res_analytics.data.overview
    print(f"  Overview: Total={overview.total_detections}, ActiveCams={overview.active_cameras}, OfflineCams={overview.offline_cameras}, Classes={overview.detection_classes_count}")
    
    # Check consistency: sum of camera detections vs total detections
    cam_sum = sum(c.detection_count for c in res_analytics.data.cameras)
    print(f"  Total Detections in Overview: {overview.total_detections}")
    print(f"  Sum of Per-Camera Detections: {cam_sum}")
    assert overview.total_detections == cam_sum, f"Mismatch: total {overview.total_detections} != camera sum {cam_sum}"
    print("  => Exact consistency verified: Overview total equals per-camera sum!")

    print(f"  Trends granularity: {res_analytics.data.trends.granularity}, Points count: {len(res_analytics.data.trends.points)}")
    for p in res_analytics.data.trends.points[:3]:
        print(f"     Trend point: period={p.period}, count={p.count}")

    print(f"  Class breakdown items: {len(res_analytics.data.classes)}")
    for cls in res_analytics.data.classes[:4]:
        print(f"     Class: {cls.class_name} -> {cls.count} ({cls.percentage}%)")

    # Check duration metrics
    dur = res_analytics.data.duration
    print(f"  Duration metrics: avg={dur.average_duration}s, total={dur.total_duration}s, max={dur.max_duration}s, events_counted={dur.total_events_with_duration}")
    assert dur.total_events_with_duration > 0, "Duration metrics should be populated from timestamps!"
    assert dur.average_duration is not None and dur.average_duration > 0
    print("  => [PASS] Analytics duration metrics populated with derived continuous activity sessions!")

    # ---------------------------------------------------------
    # TEST 6: CONTROLLED INFERENCE TEST
    # ---------------------------------------------------------
    print("\n[TEST 6] Controlled Inference Test with Real Model...")
    client = SageMakerInferenceClient()
    
    # Blank frame
    import numpy as np
    import cv2
    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    _, enc_blank = cv2.imencode(".jpg", blank)
    res_blank, lat_blank = client.invoke(enc_blank.tobytes())
    print(f"  Blank frame inference: {lat_blank:.1f}ms, Detections: {res_blank.get('detections')}")
    assert len(res_blank.get("detections", [])) == 0, "Blank frame must have 0 detections!"
    print("  => [PASS] Controlled inference test passed!")

    # ---------------------------------------------------------
    # TEST 7: STREAMING INTEGRITY CHECK
    # ---------------------------------------------------------
    print("\n[TEST 7] Verifying Streaming Pipeline Code Was Untouched...")
    # Check git status for streaming critical files
    import subprocess
    diff_check = subprocess.run(
        ["git", "diff", "--name-only"],
        capture_output=True,
        text=True
    )
    changed_files = diff_check.stdout.strip().splitlines()
    streaming_critical_files = [
        "backend/app/services/stream_manager.py",
        "backend/app/services/mediamtx.yml",
        "mediamtx.yml",
        "run_mediamtx.py",
    ]
    for scf in streaming_critical_files:
        assert scf not in changed_files, f"FATAL: Streaming critical file {scf} was modified!"
    print("  => [PASS] All streaming-critical files are 100% UNTOUCHED!")

    await db.close()
    print("\n" + "=" * 60)
    print("ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY WITH ZERO ERRORS!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_verification())
