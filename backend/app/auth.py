from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import secrets
from typing import Any
import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, Response, status
import jwt
from jwt.exceptions import PyJWTError

from backend.app.config import settings
from backend.app.db import db
from backend.app.models import User

LOGGER = logging.getLogger("camera.platform.auth")


# --- Password Hashing with Bcrypt ---

def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


# --- JWT Token Management ---

def create_access_token(user: User) -> str:
    """Creates a signed JWT containing minimal identity claims."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user.id,
        "email": user.email,
        "org": user.organization_id,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodes and verifies a JWT token. Raises PyJWTError on failure."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# --- Cookie Helpers ---

def set_auth_cookie(response: Response, token: str) -> None:
    """Sets a secure HttpOnly cookie for browser authentication."""
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=settings.cookie_http_only,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Clears the authentication cookie."""
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        httponly=settings.cookie_http_only,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


# --- Application-Level Camera Credential Encryption ---

def _get_fernet() -> Fernet:
    """Derives a deterministic 32-byte urlsafe Fernet key from CAMERA_ENCRYPTION_KEY."""
    raw_key = settings.camera_encryption_key.encode("utf-8")
    derived = base64.urlsafe_b64encode(hashlib.sha256(raw_key).digest())
    return Fernet(derived)


def encrypt_camera_credentials(credentials: dict[str, Any]) -> str:
    """Encrypts camera credentials (e.g. username/password) into a safe ciphertext string."""
    fernet = _get_fernet()
    serialized = json.dumps(credentials).encode("utf-8")
    return fernet.encrypt(serialized).decode("utf-8")


def decrypt_camera_credentials(ciphertext: str) -> dict[str, Any]:
    """Decrypts ciphertext into original credentials dictionary."""
    if not ciphertext:
        return {}
    fernet = _get_fernet()
    try:
        decrypted = fernet.decrypt(ciphertext.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except (InvalidToken, Exception) as exc:
        LOGGER.error("Failed to decrypt camera credentials: %s", exc)
        return {}


# --- Current User Dependency (Fail-Closed) ---

async def get_current_user(request: Request) -> User:
    """
    Extracts authentication cookie or Authorization header, validates JWT,
    and fetches active user from MongoDB.
    """
    token = request.cookies.get(settings.cookie_name)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session token payload.",
            )
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid.",
        )

    try:
        user_doc = await db.users.find_one({"id": user_id})
    except Exception as exc:
        LOGGER.error("Database query failed during authentication: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        )

    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
        )

    user = User(**user_doc)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


async def get_optional_user(request: Request) -> User | None:
    """Returns current user if authenticated, otherwise None (does not raise 401)."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


# --- Edge Gateway Token Helpers ---

def hash_edge_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_edge_token(plain_token: str, token_hash: str) -> bool:
    return secrets.compare_digest(hash_edge_token(plain_token), token_hash)
