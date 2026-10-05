from __future__ import annotations

from typing import Any, Callable
from fastapi import Depends, HTTPException, status

from backend.app.auth import get_current_user
from backend.app.models import User, UserRole

# Explicit role permission sets
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.SUPER_ADMIN: {
        "org:create",
        "org:read",
        "org:update",
        "org:delete",
        "user:create",
        "user:read",
        "user:update",
        "user:delete",
        "site:create",
        "site:read",
        "site:update",
        "site:delete",
        "camera:create",
        "camera:read",
        "camera:update",
        "camera:delete",
        "stream:read",
        "stream:control",
        "audit:read",
        "system:manage",
        "detection:create",
        "detection:read",
        "analytics:read",
    },
    UserRole.ORG_ADMIN: {
        "org:read",
        "org:update",
        "user:create",
        "user:read",
        "user:update",
        "user:delete",
        "site:create",
        "site:read",
        "site:update",
        "site:delete",
        "camera:create",
        "camera:read",
        "camera:update",
        "camera:delete",
        "stream:read",
        "stream:control",
        "audit:read",
        "detection:create",
        "detection:read",
        "analytics:read",
    },
    UserRole.OPERATOR: {
        "org:read",
        "user:read",
        "site:read",
        "camera:read",
        "camera:update",
        "stream:read",
        "stream:control",
        "detection:create",
        "detection:read",
        "analytics:read",
    },
    UserRole.VIEWER: {
        "org:read",
        "site:read",
        "camera:read",
        "stream:read",
        "detection:read",
        "analytics:read",
    },
}


def has_permission(role: UserRole, permission: str) -> bool:
    """Checks if a given role possesses the specified permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_role(*allowed_roles: UserRole) -> Callable:
    """Dependency that enforces user role membership."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return current_user
    return role_checker


def require_permission(permission: str) -> Callable:
    """Dependency that enforces explicit granular permissions."""
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Missing required permission: '{permission}'",
            )
        return current_user
    return permission_checker


def get_tenant_filter(current_user: User, base_filter: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    CRITICAL SERVER-SIDE TENANT ISOLATION:
    Ensures that queries strictly filter by current_user.organization_id.
    Only SUPER_ADMIN may query across organizations.
    """
    query = dict(base_filter) if base_filter else {}
    if current_user.role == UserRole.SUPER_ADMIN:
        return query

    query["organization_id"] = current_user.organization_id
    return query
