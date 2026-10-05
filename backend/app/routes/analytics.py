from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import logging
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.app.db import db
from backend.app.models import CameraStatus, User
from backend.app.permissions import get_tenant_filter, require_permission
from backend.app.routes.detections import build_detection_filter
from backend.app.schemas import ApiResponse

LOGGER = logging.getLogger("camera.platform.routes.analytics")
router = APIRouter(prefix="/analytics", tags=["Analytics"])


class DetectionTrendPoint(BaseModel):
    period: str
    count: int


class DetectionClassItem(BaseModel):
    class_name: str
    count: int
    percentage: float


class CameraAnalyticsItem(BaseModel):
    camera_id: str
    camera_name: str
    count: int
    percentage: float


class AnalyticsOverview(BaseModel):
    total_detections: int
    active_cameras: int
    offline_cameras: int
    detection_classes_count: int


class FullAnalytics(BaseModel):
    overview: AnalyticsOverview
    trends: list[DetectionTrendPoint]
    classes: list[DetectionClassItem]
    cameras: list[CameraAnalyticsItem]


@router.get("", response_model=ApiResponse[FullAnalytics])
async def get_full_analytics(
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    camera_id: Annotated[str | None, Query()] = None,
    class_name: Annotated[str | None, Query()] = None,
    min_confidence: Annotated[float | None, Query()] = None,
    granularity: Annotated[str, Query()] = "day",
    current_user: User = Depends(require_permission("analytics:read")),
):
    """Computes consolidated analytics for the operator dashboard."""
    filter_query = build_detection_filter(
        current_user=current_user,
        date_from=date_from,
        date_to=date_to,
        camera_id=camera_id,
        class_name=class_name,
        min_confidence=min_confidence,
    )

    total_detections = await db.detection_events.count_documents(filter_query)

    # Active / Offline cameras count
    cam_query = get_tenant_filter(current_user)
    active_cameras = await db.cameras.count_documents({**cam_query, "status": CameraStatus.ONLINE.value})
    offline_cameras = await db.cameras.count_documents({**cam_query, "status": CameraStatus.OFFLINE.value})

    # Class breakdown
    class_counts: dict[str, int] = defaultdict(int)
    camera_counts: dict[str, int] = defaultdict(int)
    trend_counts: dict[str, int] = defaultdict(int)

    # Fetch camera name map
    cam_cursor = db.cameras.find(cam_query, {"id": 1, "name": 1})
    cam_map = {c["id"]: c.get("name", c["id"]) async for c in cam_cursor}

    # Aggregate detections
    cursor = db.detection_events.find(filter_query, {"class_name": 1, "camera_id": 1, "timestamp": 1}).limit(2000)
    async for doc in cursor:
        c_name = doc.get("class_name", "unknown")
        class_counts[c_name] += 1

        c_id = doc.get("camera_id", "unknown")
        camera_counts[c_id] += 1

        ts = doc.get("timestamp")
        if isinstance(ts, datetime):
            period_str = ts.strftime("%Y-%m-%d")
        else:
            period_str = str(ts)[:10] if ts else "unknown"
        trend_counts[period_str] += 1

    # Format classes
    classes_list = [
        DetectionClassItem(
            class_name=cls,
            count=cnt,
            percentage=round((cnt / total_detections) * 100, 1) if total_detections > 0 else 0.0,
        )
        for cls, cnt in sorted(class_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    # Format cameras
    cameras_list = [
        CameraAnalyticsItem(
            camera_id=cid,
            camera_name=cam_map.get(cid, cid),
            count=cnt,
            percentage=round((cnt / total_detections) * 100, 1) if total_detections > 0 else 0.0,
        )
        for cid, cnt in sorted(camera_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    # Format trends
    trends_list = [
        DetectionTrendPoint(period=p, count=cnt)
        for p, cnt in sorted(trend_counts.items())
    ]

    overview = AnalyticsOverview(
        total_detections=total_detections,
        active_cameras=active_cameras,
        offline_cameras=offline_cameras,
        detection_classes_count=len(class_counts),
    )

    return ApiResponse(
        success=True,
        data=FullAnalytics(
            overview=overview,
            trends=trends_list,
            classes=classes_list,
            cameras=cameras_list,
        ),
    )
