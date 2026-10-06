from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import logging
import re
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.app.auth import get_current_user
from backend.app.db import db
from backend.app.models import DetectionEvent, DetectionItem, User, UserRole, generate_uuid, utc_now
from backend.app.permissions import get_tenant_filter, require_permission
from backend.app.schemas import (
    ApiResponse,
    DetectionEventCreate,
    DetectionEventResponse,
    DetectionLogsResponse,
)
from backend.app.websocket_manager import websocket_manager

LOGGER = logging.getLogger("camera.platform.routes.detections")
router = APIRouter(tags=["Detections"])


def parse_datetime(val: str | None) -> datetime | None:
    if not val or not val.strip():
        return None
    clean = val.strip()
    try:
        dt = datetime.fromisoformat(clean.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        dt = datetime.strptime(clean, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def build_detection_filter(
    current_user: User,
    date_from: str | None = None,
    date_to: str | None = None,
    camera_id: str | None = None,
    class_name: str | None = None,
    min_confidence: float | None = None,
    search: str | None = None,
) -> dict:
    conditions: list[dict[str, Any]] = []

    if camera_id and camera_id.strip():
        conditions.append({"camera_id": camera_id.strip()})

    if class_name and class_name.strip():
        cls_pattern = f"^{re.escape(class_name.strip())}$"
        conditions.append({
            "$or": [
                {"class_name": {"$regex": cls_pattern, "$options": "i"}},
                {"detections.class_name": {"$regex": cls_pattern, "$options": "i"}},
            ]
        })

    if min_confidence is not None and min_confidence > 0:
        threshold = min_confidence / 100.0 if min_confidence > 1.0 else min_confidence
        conditions.append({"confidence": {"$gte": round(threshold, 4)}})

    dt_from = parse_datetime(date_from)
    dt_to = parse_datetime(date_to)

    if dt_from or dt_to:
        str_cond: dict[str, str] = {}
        dt_cond: dict[str, datetime] = {}
        if dt_from:
            str_cond["$gte"] = dt_from.isoformat().replace("+00:00", "Z")
            dt_cond["$gte"] = dt_from
        if dt_to:
            clean_to = date_to.strip() if date_to else ""
            if len(clean_to) == 10:
                dt_to = dt_to.replace(hour=23, minute=59, second=59, microsecond=999999)
            str_cond["$lte"] = dt_to.isoformat().replace("+00:00", "Z")
            dt_cond["$lte"] = dt_to
        conditions.append({
            "$or": [
                {"timestamp": str_cond},
                {"timestamp": dt_cond},
            ]
        })

    if search and search.strip():
        term = re.escape(search.strip())
        conditions.append({
            "$or": [
                {"class_name": {"$regex": term, "$options": "i"}},
                {"detections.class_name": {"$regex": term, "$options": "i"}},
                {"camera_id": {"$regex": term, "$options": "i"}},
                {"camera_name": {"$regex": term, "$options": "i"}},
            ]
        })

    base_filter: dict[str, Any] = {}
    if len(conditions) == 1:
        base_filter = conditions[0]
    elif len(conditions) > 1:
        base_filter = {"$and": conditions}

    return get_tenant_filter(current_user, base_filter)


def format_detection_response(doc: dict) -> DetectionEventResponse:
    raw_dets = doc.get("detections", [])
    if raw_dets:
        items = [
            DetectionItem(
                class_id=d.get("class_id", 0),
                class_name=d.get("class_name", "object"),
                confidence=d.get("confidence", 0.0),
                bbox=d.get("bbox", []),
            )
            for d in raw_dets
        ]
    elif doc.get("class_name"):
        items = [
            DetectionItem(
                class_id=0,
                class_name=doc.get("class_name", "object"),
                confidence=doc.get("confidence", 0.0),
                bbox=doc.get("bounding_box") or [],
            )
        ]
    else:
        items = []

    ts = doc.get("timestamp")
    if isinstance(ts, str):
        ts = parse_datetime(ts) or utc_now()
    created = doc.get("created_at")
    if isinstance(created, str):
        created = parse_datetime(created) or utc_now()

    return DetectionEventResponse(
        id=doc.get("id", ""),
        camera_id=doc.get("camera_id", ""),
        camera_name=doc.get("camera_name"),
        site_id=doc.get("site_id"),
        timestamp=ts or utc_now(),
        class_name=doc.get("class_name", "unknown"),
        confidence=doc.get("confidence", 0.0),
        bounding_box=doc.get("bounding_box"),
        detections=items,
        model_name=doc.get("model_name", "yolo"),
        inference_latency_ms=doc.get("inference_latency_ms", 0.0),
        created_at=created or utc_now(),
    )


# --- Detections Collection Queries ---

@router.get("/detections", response_model=ApiResponse[DetectionLogsResponse])
@router.get("/detection-logs", response_model=ApiResponse[DetectionLogsResponse])
async def list_detections(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    camera_id: Annotated[str | None, Query()] = None,
    class_name: Annotated[str | None, Query()] = None,
    min_confidence: Annotated[float | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    current_user: User = Depends(require_permission("detection:read")),
):
    """
    Returns paginated AI detection events with filtering by:
    - camera_id
    - class_name (e.g. person, car)
    - min_confidence
    - date_from, date_to
    - search
    """
    filter_query = build_detection_filter(
        current_user=current_user,
        date_from=date_from,
        date_to=date_to,
        camera_id=camera_id,
        class_name=class_name,
        min_confidence=min_confidence,
        search=search,
    )

    skip = (page - 1) * page_size
    total = await db.detection_events.count_documents(filter_query)
    cursor = db.detection_events.find(filter_query).sort("timestamp", -1).skip(skip).limit(page_size)

    items = [format_detection_response(doc) async for doc in cursor]
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return ApiResponse(
        success=True,
        data=DetectionLogsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )


@router.get("/detections/{detection_id}", response_model=ApiResponse[DetectionEventResponse])
async def get_detection(
    detection_id: str,
    current_user: User = Depends(require_permission("detection:read")),
):
    """Retrieves a single detection event by ID."""
    query = get_tenant_filter(current_user, {"id": detection_id})
    doc = await db.detection_events.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Detection event not found.")
    return ApiResponse(success=True, data=format_detection_response(doc))


@router.get("/cameras/{camera_id}/detections", response_model=ApiResponse[list[DetectionEventResponse]])
async def get_camera_detections(
    camera_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    current_user: User = Depends(require_permission("detection:read")),
):
    """Retrieves recent detections for a specific camera."""
    query = get_tenant_filter(current_user, {"camera_id": camera_id})
    cursor = db.detection_events.find(query).sort("timestamp", -1).limit(limit)
    items = [format_detection_response(doc) async for doc in cursor]
    return ApiResponse(success=True, data=items)


@router.get("/cameras/{camera_id}/detections/latest", response_model=ApiResponse[DetectionEventResponse | None])
async def get_camera_latest_detection(
    camera_id: str,
    current_user: User = Depends(require_permission("detection:read")),
):
    """Retrieves the single most recent detection event for a camera."""
    query = get_tenant_filter(current_user, {"camera_id": camera_id})
    doc = await db.detection_events.find_one(query, sort=[("timestamp", -1)])
    if not doc:
        return ApiResponse(success=True, data=None)
    return ApiResponse(success=True, data=format_detection_response(doc))


@router.post("/detection-events", response_model=ApiResponse[DetectionEventResponse], status_code=status.HTTP_201_CREATED)
async def ingest_detection_event(
    payload: DetectionEventCreate,
    current_user: User = Depends(require_permission("detection:create")),
):
    """Ingests a detection event and broadcasts to WebSocket clients."""
    camera_doc = await db.cameras.find_one({"id": payload.camera_id})
    if not camera_doc:
        raise HTTPException(status_code=404, detail=f"Camera '{payload.camera_id}' not found.")

    org_id = camera_doc.get("organization_id")
    event = DetectionEvent(
        id=generate_uuid(),
        organization_id=org_id,
        site_id=payload.site_id or camera_doc.get("site_id"),
        camera_id=payload.camera_id,
        camera_name=camera_doc.get("name"),
        timestamp=payload.timestamp or utc_now(),
        class_name=payload.class_name,
        confidence=payload.confidence,
        bounding_box=payload.bounding_box,
        duration_seconds=payload.duration_seconds,
        track_id=payload.track_id,
        detections=payload.detections,
        model_name=payload.model_name,
        model_endpoint=payload.model_endpoint,
        inference_latency_ms=payload.inference_latency_ms,
        created_at=utc_now(),
    )

    doc = event.model_dump(mode="json")
    await db.detection_events.insert_one(doc)

    # Broadcast to WebSocket clients
    await websocket_manager.broadcast({
        "type": "detection_event",
        "data": {
            "id": event.id,
            "camera_id": event.camera_id,
            "camera_name": event.camera_name,
            "timestamp": event.timestamp.isoformat(),
            "class_name": event.class_name,
            "confidence": event.confidence,
            "bounding_box": event.bounding_box,
        },
    })

    return ApiResponse(success=True, data=format_detection_response(doc))


@router.get("/detection-logs/export")
async def export_detection_logs_csv(
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    camera_id: Annotated[str | None, Query()] = None,
    class_name: Annotated[str | None, Query()] = None,
    min_confidence: Annotated[float | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    current_user: User = Depends(require_permission("detection:read")),
):
    """Exports filtered detection logs as a CSV download."""
    query = build_detection_filter(
        current_user=current_user,
        date_from=date_from,
        date_to=date_to,
        camera_id=camera_id,
        class_name=class_name,
        min_confidence=min_confidence,
        search=search,
    )

    cursor = db.detection_events.find(query).sort("timestamp", -1).limit(5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Event ID",
        "Timestamp (UTC)",
        "Camera ID",
        "Camera Name",
        "Detected Class",
        "Confidence",
        "Model",
        "Inference Latency (ms)",
        "Bounding Box [x1, y1, x2, y2]",
    ])

    async for doc in cursor:
        writer.writerow([
            doc.get("id", ""),
            str(doc.get("timestamp", "")),
            doc.get("camera_id", ""),
            doc.get("camera_name", ""),
            doc.get("class_name", ""),
            f"{doc.get('confidence', 0.0):.2%}",
            doc.get("model_name", "yolo"),
            doc.get("inference_latency_ms", 0.0),
            str(doc.get("bounding_box", "")),
        ])

    csv_data = output.getvalue()
    filename = f"cctv-detections-{utc_now().strftime('%Y-%m-%d')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
