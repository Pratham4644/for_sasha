from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from backend.app.db import db
from backend.app.models import AuditLog, User, generate_uuid, utc_now
from backend.app.permissions import get_tenant_filter, require_permission
from backend.app.schemas import ApiResponse

LOGGER = logging.getLogger("camera.platform.routes.logs")
router = APIRouter(tags=["Audit Logs"])


class AuditLogEntrySchema(BaseModel):
    id: str
    organization_id: str | None = None
    user_id: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    timestamp: str
    request_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditLogsResponse(BaseModel):
    items: list[AuditLogEntrySchema]
    total: int
    page: int = 1
    page_size: int = 25
    total_pages: int = 0


async def record_audit_log(
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    user_id: str | None = None,
    organization_id: str | None = None,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Asynchronously writes a real audit log entry to MongoDB."""
    if not db.is_connected:
        return
    try:
        entry = AuditLog(
            id=generate_uuid(),
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            created_at=utc_now(),
        )
        doc = entry.model_dump(mode="json")
        doc["timestamp"] = entry.created_at.isoformat()
        if request_id:
            doc["request_id"] = request_id
        await db.logs.insert_one(doc)
    except Exception as exc:
        LOGGER.debug("Failed to record audit log: %s", exc)


@router.get("/logs", response_model=ApiResponse[AuditLogsResponse])
@router.get("/audit-logs", response_model=ApiResponse[AuditLogsResponse])
async def list_audit_logs(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    resource_type: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    current_user: User = Depends(require_permission("audit:read")),
):
    """
    Returns paginated audit log entries.
    If the audit collection is empty, returns HTTP 200 with an empty list. Never returns HTTP 404.
    """
    query: dict[str, Any] = {}
    if resource_type and resource_type.strip():
        query["resource_type"] = resource_type.strip()
    if action and action.strip():
        query["action"] = action.strip()

    tenant_query = get_tenant_filter(current_user, query)

    # Use db.logs or db.audit_logs collection
    coll = db.logs if db.is_connected else None
    if coll is None:
        return ApiResponse(
            success=True,
            data=AuditLogsResponse(items=[], total=0, page=page, page_size=page_size, total_pages=0),
        )

    total = await coll.count_documents(tenant_query)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    skip = (page - 1) * page_size

    items: list[AuditLogEntrySchema] = []
    if total > 0:
        cursor = coll.find(tenant_query).sort([("created_at", -1), ("timestamp", -1), ("_id", -1)]).skip(skip).limit(page_size)
        async for doc in cursor:
            ts = doc.get("timestamp") or doc.get("created_at")
            if isinstance(ts, datetime):
                ts_str = ts.isoformat().replace("+00:00", "Z")
            else:
                ts_str = str(ts) if ts else utc_now().isoformat()

            items.append(
                AuditLogEntrySchema(
                    id=doc.get("id", str(doc.get("_id", generate_uuid()))),
                    organization_id=doc.get("organization_id"),
                    user_id=doc.get("user_id"),
                    action=doc.get("action", "unknown"),
                    resource_type=doc.get("resource_type", "system"),
                    resource_id=doc.get("resource_id"),
                    timestamp=ts_str,
                    request_id=doc.get("request_id"),
                    details=doc.get("details", {}),
                )
            )

    return ApiResponse(
        success=True,
        data=AuditLogsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )
