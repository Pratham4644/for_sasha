from __future__ import annotations

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.app.auth import get_current_user, hash_password
from backend.app.db import db
from backend.app.models import User, UserRole, utc_now
from backend.app.permissions import require_role
from backend.app.schemas import ApiResponse, UserCreate, UserResponse

LOGGER = logging.getLogger("camera.platform.routes.users")
router = APIRouter(prefix="/users", tags=["Users"])


class UserUpdate(BaseModel):
    name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = None


@router.post("", response_model=ApiResponse[UserResponse], status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreate,
    current_user: User = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN)),
):
    """Creates a new user within organization."""
    target_org_id = req.organization_id if current_user.role == UserRole.SUPER_ADMIN and req.organization_id else current_user.organization_id

    existing = await db.users.find_one({"email": req.email.lower().strip()})
    if existing:
        raise HTTPException(status_code=409, detail=f"Email '{req.email}' is already registered.")

    user = User(
        organization_id=target_org_id,
        email=req.email.lower().strip(),
        name=req.name.strip(),
        password_hash=hash_password(req.password),
        role=req.role,
        is_active=True,
    )
    await db.users.insert_one(user.model_dump(mode="json"))

    return ApiResponse(
        success=True,
        data=UserResponse(
            id=user.id,
            organization_id=user.organization_id,
            email=user.email,
            name=user.name,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        ),
    )


@router.get("", response_model=ApiResponse[list[UserResponse]])
async def list_users(
    current_user: User = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN)),
):
    """Lists users in the caller's organization."""
    query: dict = {}
    if current_user.role != UserRole.SUPER_ADMIN:
        query["organization_id"] = current_user.organization_id

    cursor = db.users.find(query).sort("created_at", -1)
    users = [
        UserResponse(
            id=doc.get("id"),
            organization_id=doc.get("organization_id"),
            email=doc.get("email"),
            name=doc.get("name"),
            role=doc.get("role"),
            is_active=doc.get("is_active", True),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )
        async for doc in cursor
    ]
    return ApiResponse(success=True, data=users)


@router.delete("/{user_id}", response_model=ApiResponse[dict[str, str]])
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN)),
):
    """Deletes a user."""
    query = {"id": user_id}
    if current_user.role != UserRole.SUPER_ADMIN:
        query["organization_id"] = current_user.organization_id

    res = await db.users.delete_one(query)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    return ApiResponse(success=True, data={"message": "User deleted successfully."})
