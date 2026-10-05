from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.auth import get_current_user
from backend.app.db import db
from backend.app.models import Organization, User, UserRole
from backend.app.permissions import require_role
from backend.app.schemas import ApiResponse

LOGGER = logging.getLogger("camera.platform.routes.organizations")
router = APIRouter(prefix="/organizations", tags=["Organizations"])


class OrganizationResponse(BaseModel):
    id: str
    name: str
    created_at: Any
    updated_at: Any


@router.get("/current", response_model=ApiResponse[OrganizationResponse])
async def get_current_organization(current_user: User = Depends(get_current_user)):
    """Retrieves current user's organization."""
    doc = await db.organizations.find_one({"id": current_user.organization_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return ApiResponse(
        success=True,
        data=OrganizationResponse(
            id=doc.get("id"),
            name=doc.get("name"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        ),
    )


@router.get("", response_model=ApiResponse[list[OrganizationResponse]])
async def list_organizations(current_user: User = Depends(require_role(UserRole.SUPER_ADMIN))):
    """Lists all organizations (Super Admin only)."""
    cursor = db.organizations.find({}).sort("created_at", -1)
    orgs = [
        OrganizationResponse(
            id=doc.get("id"),
            name=doc.get("name"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )
        async for doc in cursor
    ]
    return ApiResponse(success=True, data=orgs)
