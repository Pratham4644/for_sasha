from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from backend.app.auth import (
    clear_auth_cookie,
    create_access_token,
    get_current_user,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from backend.app.db import db
from backend.app.models import Organization, User, UserRole, generate_uuid, utc_now
from backend.app.schemas import ApiResponse, LoginRequest, LoginResponse

LOGGER = logging.getLogger("camera.platform.routes.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    organization_name: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    current_password: str | None = None
    new_password: str | None = None


@router.post("/register", response_model=ApiResponse[dict[str, Any]], status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, response: Response):
    """Registers a new user and organization."""
    clean_email = req.email.lower().strip()
    clean_name = req.name.strip()
    org_name = (req.organization_name or f"{clean_name}'s Org").strip()

    existing_user = await db.users.find_one({"email": clean_email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{clean_email}' already exists.",
        )

    # Create Organization
    org = Organization(name=org_name)
    await db.organizations.insert_one(org.model_dump(mode="json"))

    # Create User with ORG_ADMIN
    user = User(
        organization_id=org.id,
        email=clean_email,
        name=clean_name,
        password_hash=hash_password(req.password),
        role=UserRole.ORG_ADMIN,
        is_active=True,
    )
    await db.users.insert_one(user.model_dump(mode="json"))

    token = create_access_token(user)
    set_auth_cookie(response, token)

    return ApiResponse(
        success=True,
        data={
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "organization_id": user.organization_id,
            "token": token,
        },
    )


@router.post("/login", response_model=ApiResponse[dict[str, Any]])
async def login(req: LoginRequest, response: Response):
    """Authenticates with email and password, setting an HttpOnly cookie and returning token."""
    clean_email = req.email.lower().strip()
    user_doc = await db.users.find_one({"email": clean_email})

    if not user_doc or not verify_password(req.password, user_doc.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user = User(**user_doc)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    token = create_access_token(user)
    set_auth_cookie(response, token)

    from backend.app.routes.logs import record_audit_log
    await record_audit_log(
        action="user:login",
        resource_type="auth",
        resource_id=user.id,
        user_id=user.id,
        organization_id=user.organization_id,
        details={"email": user.email, "role": user.role.value if hasattr(user.role, "value") else str(user.role)},
    )

    return ApiResponse(
        success=True,
        data={
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "organization_id": user.organization_id,
            "token": token,
        },
    )


@router.post("/logout", response_model=ApiResponse[dict[str, str]])
async def logout(response: Response):
    """Clears session cookie."""
    clear_auth_cookie(response)
    return ApiResponse(success=True, data={"message": "Logged out successfully."})


@router.get("/me", response_model=ApiResponse[dict[str, Any]])
async def get_me(current_user: User = Depends(get_current_user)):
    """Returns profile for currently authenticated user."""
    return ApiResponse(
        success=True,
        data={
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
            "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            "organization_id": current_user.organization_id,
            "created_at": current_user.created_at,
        },
    )


@router.patch("/profile", response_model=ApiResponse[dict[str, Any]])
async def update_profile(req: ProfileUpdate, current_user: User = Depends(get_current_user)):
    """Updates user profile or password."""
    updates: dict = {"updated_at": utc_now()}
    if req.name and req.name.strip():
        updates["name"] = req.name.strip()

    if req.new_password:
        if not req.current_password or not verify_password(req.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password verification failed.")
        updates["password_hash"] = hash_password(req.new_password)

    await db.users.update_one({"id": current_user.id}, {"$set": updates})
    updated = await db.users.find_one({"id": current_user.id})
    user = User(**updated)

    return ApiResponse(
        success=True,
        data={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "organization_id": user.organization_id,
        },
    )
