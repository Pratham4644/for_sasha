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


class DetectionTrendsResponse(BaseModel):
    granularity: str
    points: list[DetectionTrendPoint]


class DetectionClassItem(BaseModel):
    class_name: str
    count: int
    percentage: float


class CameraAnalyticsItem(BaseModel):
    camera_id: str
    camera_name: str
    status: str
    detection_count: int
    last_activity: str | None = None


class DurationStatistics(BaseModel):
    average_duration: float | None = None
    total_duration: float | None = None
    max_duration: float | None = None
    total_events_with_duration: int = 0


class AnalyticsOverview(BaseModel):
    total_detections: int
    active_cameras: int
    offline_cameras: int
    detection_classes_count: int


class FullAnalytics(BaseModel):
    overview: AnalyticsOverview
    trends: DetectionTrendsResponse
    classes: list[DetectionClassItem]
    cameras: list[CameraAnalyticsItem]
    duration: DurationStatistics


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
    """Computes consolidated canonical analytics for the operator dashboard using full database aggregation."""
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
    offline_cameras = await db.cameras.count_documents({**cam_query, "status": {"$ne": CameraStatus.ONLINE.value}})

    # Fetch registered cameras map
    cam_cursor = db.cameras.find(cam_query, {"id": 1, "name": 1, "status": 1, "updated_at": 1})
    registered_cams: dict[str, dict[str, Any]] = {c["id"]: c async for c in cam_cursor}

    # 1. Aggregate Classes (canonical breakdown across 100% of matching records)
    class_pipeline: list[dict[str, Any]] = []
    if filter_query:
        class_pipeline.append({"$match": filter_query})
    class_pipeline.extend([
        {"$group": {"_id": "$class_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    cur_cls = await db.detection_events.aggregate(class_pipeline)
    raw_classes = [c async for c in cur_cls]

    classes_list = [
        DetectionClassItem(
            class_name=str(c.get("_id") or "unknown"),
            count=c.get("count", 0),
            percentage=round((c.get("count", 0) / total_detections) * 100, 1) if total_detections > 0 else 0.0,
        )
        for c in raw_classes[:12]
    ]

    # 2. Aggregate Per-Camera Counts and Last Activity
    cam_pipeline: list[dict[str, Any]] = []
    if filter_query:
        cam_pipeline.append({"$match": filter_query})
    cam_pipeline.extend([
        {"$group": {
            "_id": "$camera_id",
            "count": {"$sum": 1},
            "last_activity": {"$max": "$timestamp"},
            "camera_name": {"$first": "$camera_name"},
        }},
        {"$sort": {"count": -1}},
    ])
    cur_cam = await db.detection_events.aggregate(cam_pipeline)
    cam_counts_map: dict[str, dict[str, Any]] = {c.get("_id"): c async for c in cur_cam if c.get("_id")}

    # Build comprehensive camera table (including registered cameras with 0 detections)
    cameras_list: list[CameraAnalyticsItem] = []
    seen_cids = set()

    for cid, cdata in registered_cams.items():
        seen_cids.add(cid)
        agg = cam_counts_map.get(cid, {})
        det_cnt = agg.get("count", 0)
        last_act = agg.get("last_activity")
        if not last_act and cdata.get("updated_at"):
            u = cdata.get("updated_at")
            last_act = u.isoformat() if isinstance(u, datetime) else str(u)

        cameras_list.append(
            CameraAnalyticsItem(
                camera_id=cid,
                camera_name=cdata.get("name", cid),
                status=cdata.get("status", CameraStatus.ONLINE.value),
                detection_count=det_cnt,
                last_activity=str(last_act) if last_act else None,
            )
        )

    # Also include any historic cameras present in detection data but no longer active
    for cid, agg in cam_counts_map.items():
        if cid not in seen_cids:
            cameras_list.append(
                CameraAnalyticsItem(
                    camera_id=cid,
                    camera_name=agg.get("camera_name") or cid,
                    status=CameraStatus.OFFLINE.value,
                    detection_count=agg.get("count", 0),
                    last_activity=str(agg.get("last_activity")) if agg.get("last_activity") else None,
                )
            )

    cameras_list.sort(key=lambda c: c.detection_count, reverse=True)

    # 3. Aggregate Trends by Granularity
    substr_len = 10  # default day "YYYY-MM-DD"
    if granularity == "hour":
        substr_len = 13  # "YYYY-MM-DDTHH"
    elif granularity == "month":
        substr_len = 7   # "YYYY-MM"

    trend_pipeline: list[dict[str, Any]] = []
    if filter_query:
        trend_pipeline.append({"$match": filter_query})
    trend_pipeline.extend([
        {"$group": {
            "_id": {"$substrCP": ["$timestamp", 0, substr_len]},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ])
    cur_trend = await db.detection_events.aggregate(trend_pipeline)
    raw_trends = [t async for t in cur_trend]

    trends_list: list[DetectionTrendPoint] = []
    for t in raw_trends:
        p_val = str(t.get("_id") or "")
        if granularity == "hour" and "T" in p_val:
            p_val = p_val.replace("T", " ") + ":00"
        trends_list.append(DetectionTrendPoint(period=p_val, count=t.get("count", 0)))

    # 4. Duration Statistics
    # Check if any events store duration_seconds > 0
    dur_pipeline: list[dict[str, Any]] = [
        {"$match": {**filter_query, "duration_seconds": {"$gt": 0}}},
        {"$group": {
            "_id": None,
            "avg": {"$avg": "$duration_seconds"},
            "sum": {"$sum": "$duration_seconds"},
            "max": {"$max": "$duration_seconds"},
            "count": {"$sum": 1},
        }},
    ]
    cur_dur = await db.detection_events.aggregate(dur_pipeline)
    raw_dur = [d async for d in cur_dur]

    if raw_dur and raw_dur[0].get("count", 0) > 0:
        d_agg = raw_dur[0]
        dur_stats = DurationStatistics(
            average_duration=round(d_agg.get("avg", 0.0), 1),
            total_duration=round(d_agg.get("sum", 0.0), 1),
            max_duration=round(d_agg.get("max", 0.0), 1),
            total_events_with_duration=d_agg.get("count", 0),
        )
    elif total_detections > 0:
        # If duration_seconds is not stored (snapshot instantaneous detections),
        # derive continuous activity session durations from actual persisted timestamps
        cursor_sessions = db.detection_events.find(
            filter_query,
            {"camera_id": 1, "timestamp": 1},
        ).sort("timestamp", 1).limit(4000)

        by_cam = defaultdict(list)
        async for doc in cursor_sessions:
            ts_val = doc.get("timestamp")
            if isinstance(ts_val, datetime):
                dt = ts_val
            elif isinstance(ts_val, str):
                try:
                    dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                except Exception:
                    continue
            else:
                continue
            by_cam[doc.get("camera_id")].append(dt)

        derived_durations: list[float] = []
        for cid, ts_list in by_cam.items():
            if not ts_list:
                continue
            sess_start = ts_list[0]
            sess_prev = ts_list[0]
            for cur_ts in ts_list[1:]:
                gap = (cur_ts - sess_prev).total_seconds()
                if gap <= 5.0:
                    sess_prev = cur_ts
                else:
                    derived_durations.append(max(1.0, (sess_prev - sess_start).total_seconds()))
                    sess_start = cur_ts
                    sess_prev = cur_ts
            derived_durations.append(max(1.0, (sess_prev - sess_start).total_seconds()))

        if derived_durations:
            dur_stats = DurationStatistics(
                average_duration=round(sum(derived_durations) / len(derived_durations), 1),
                total_duration=round(sum(derived_durations), 1),
                max_duration=round(max(derived_durations), 1),
                total_events_with_duration=len(derived_durations),
            )
        else:
            dur_stats = DurationStatistics()
    else:
        dur_stats = DurationStatistics()

    overview = AnalyticsOverview(
        total_detections=total_detections,
        active_cameras=active_cameras,
        offline_cameras=offline_cameras,
        detection_classes_count=len(raw_classes),
    )

    return ApiResponse(
        success=True,
        data=FullAnalytics(
            overview=overview,
            trends=DetectionTrendsResponse(
                granularity=granularity,
                points=trends_list,
            ),
            classes=classes_list,
            cameras=cameras_list,
            duration=dur_stats,
        ),
    )
