from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.auth import get_current_user
from backend.app.db import db
from backend.app.models import Organization, User, UserRole, utc_now
from backend.app.permissions import require_role
from backend.app.schemas import ApiResponse

LOGGER = logging.getLogger("camera.platform.routes.organizations")
router = APIRouter(prefix="/organizations", tags=["Organizations"])


class OrganizationResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_at: Any
    updated_at: Any


class OrganizationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


def _format_org(doc: dict) -> OrganizationResponse:
    return OrganizationResponse(
        id=doc.get("id", ""),
        name=doc.get("name", ""),
        description=doc.get("description"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


@router.get("/current", response_model=ApiResponse[OrganizationResponse])
async def get_current_organization(current_user: User = Depends(get_current_user)):
    """Retrieves current user's organization."""
    doc = await db.organizations.find_one({"id": current_user.organization_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return ApiResponse(success=True, data=_format_org(doc))


@router.get("/{organization_id}", response_model=ApiResponse[OrganizationResponse])
async def get_organization(
    organization_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retrieves organization by ID (matching user tenant or Super Admin)."""
    if current_user.role != UserRole.SUPER_ADMIN and current_user.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot access other organizations.")

    doc = await db.organizations.find_one({"id": organization_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return ApiResponse(success=True, data=_format_org(doc))


@router.patch("/{organization_id}", response_model=ApiResponse[OrganizationResponse])
async def update_organization(
    organization_id: str,
    body: OrganizationUpdate,
    current_user: User = Depends(get_current_user),
):
    """Updates organization profile."""
    if current_user.role not in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN):
        raise HTTPException(status_code=403, detail="Forbidden: Admin privileges required.")
    if current_user.role != UserRole.SUPER_ADMIN and current_user.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot modify other organizations.")

    doc = await db.organizations.find_one({"id": organization_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Organization not found.")

    updates: dict[str, Any] = {"updated_at": utc_now()}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.description is not None:
        updates["description"] = body.description.strip()

    await db.organizations.update_one({"id": organization_id}, {"$set": updates})
    from backend.app.routes.logs import record_audit_log
    await record_audit_log(
        action="organization:update",
        resource_type="organization",
        resource_id=organization_id,
        user_id=current_user.id,
        organization_id=organization_id,
        details={"name": body.name, "description": body.description},
    )
    updated = await db.organizations.find_one({"id": organization_id})
    return ApiResponse(success=True, data=_format_org(updated))


@router.get("", response_model=ApiResponse[list[OrganizationResponse]])
async def list_organizations(current_user: User = Depends(require_role(UserRole.SUPER_ADMIN))):
    """Lists all organizations (Super Admin only)."""
    cursor = db.organizations.find({}).sort("created_at", -1)
    orgs = [_format_org(doc) async for doc in cursor]
    return ApiResponse(success=True, data=orgs)
