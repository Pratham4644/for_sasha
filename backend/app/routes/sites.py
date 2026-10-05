from __future__ import annotations

import logging
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.auth import get_current_user
from backend.app.db import db
from backend.app.models import Site, User, UserRole, utc_now
from backend.app.permissions import get_tenant_filter, require_permission
from backend.app.schemas import ApiResponse

LOGGER = logging.getLogger("camera.platform.routes.sites")
router = APIRouter(prefix="/sites", tags=["Sites"])


class SiteCreate(BaseModel):
    name: str
    description: str | None = None


class SiteResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None = None
    created_at: Any
    updated_at: Any


@router.post("", response_model=ApiResponse[SiteResponse], status_code=status.HTTP_201_CREATED)
async def create_site(
    req: SiteCreate,
    current_user: User = Depends(require_permission("site:create")),
):
    """Creates a new site for camera organization."""
    site = Site(
        id=str(uuid.uuid4()),
        organization_id=current_user.organization_id,
        name=req.name.strip(),
        description=req.description,
    )
    await db.sites.insert_one(site.model_dump(mode="json"))
    return ApiResponse(
        success=True,
        data=SiteResponse(
            id=site.id,
            organization_id=site.organization_id,
            name=site.name,
            description=site.description,
            created_at=site.created_at,
            updated_at=site.updated_at,
        ),
    )


@router.get("", response_model=ApiResponse[list[SiteResponse]])
async def list_sites(current_user: User = Depends(require_permission("site:read"))):
    """Lists sites belonging to user's organization."""
    query = get_tenant_filter(current_user)
    cursor = db.sites.find(query).sort("created_at", -1)
    sites = [
        SiteResponse(
            id=doc.get("id"),
            organization_id=doc.get("organization_id"),
            name=doc.get("name"),
            description=doc.get("description"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )
        async for doc in cursor
    ]
    return ApiResponse(success=True, data=sites)


@router.get("/{site_id}", response_model=ApiResponse[SiteResponse])
async def get_site(site_id: str, current_user: User = Depends(require_permission("site:read"))):
    """Retrieves single site."""
    query = get_tenant_filter(current_user, {"id": site_id})
    doc = await db.sites.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Site not found.")
    return ApiResponse(
        success=True,
        data=SiteResponse(
            id=doc.get("id"),
            organization_id=doc.get("organization_id"),
            name=doc.get("name"),
            description=doc.get("description"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        ),
    )
