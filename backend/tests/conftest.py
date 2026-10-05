from __future__ import annotations

import os
import sys
import mongomock
import pytest
from starlette.testclient import TestClient

PROD_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROD_DIR not in sys.path:
    sys.path.insert(0, PROD_DIR)

from backend.app.auth import create_access_token, hash_password
from backend.app.config import settings
from backend.app.db import db
from backend.app.main import app
from backend.app.models import Organization, Site, User, UserRole


class AsyncCursor:
    def __init__(self, sync_cursor):
        self._cursor = sync_cursor

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self._cursor = self._cursor.skip(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self._cursor = self._cursor.limit(*args, **kwargs)
        return self

    def __aiter__(self):
        self._iter = iter(self._cursor)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class AsyncMockCol:
    def __init__(self, sync_col):
        self._col = sync_col

    async def find_one(self, *args, **kwargs):
        return self._col.find_one(*args, **kwargs)

    async def insert_one(self, *args, **kwargs):
        return self._col.insert_one(*args, **kwargs)

    async def update_one(self, *args, **kwargs):
        return self._col.update_one(*args, **kwargs)

    async def delete_one(self, *args, **kwargs):
        return self._col.delete_one(*args, **kwargs)

    async def delete_many(self, *args, **kwargs):
        return self._col.delete_many(*args, **kwargs)

    async def count_documents(self, *args, **kwargs):
        return self._col.count_documents(*args, **kwargs)

    def find(self, *args, **kwargs):
        return AsyncCursor(self._col.find(*args, **kwargs))

    def aggregate(self, *args, **kwargs):
        return AsyncCursor(self._col.aggregate(*args, **kwargs))

    async def distinct(self, *args, **kwargs):
        return self._col.distinct(*args, **kwargs)

    async def create_indexes(self, *args, **kwargs):
        return []


class AsyncMockDatabase:
    def __init__(self, sync_db):
        self._db = sync_db

    def __getitem__(self, name: str) -> AsyncMockCol:
        return AsyncMockCol(self._db[name])


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    """Sets up an isolated in-memory mock database before each test."""
    mock_client = mongomock.MongoClient()
    sync_db = mock_client["test_camera_ai_platform"]
    mock_async_db = AsyncMockDatabase(sync_db)
    db.db = mock_async_db
    db._connected = True

    async def mock_connect(*args, **kwargs):
        db.db = mock_async_db
        db._connected = True
        return True

    async def mock_close(*args, **kwargs):
        pass

    async def mock_ensure_indexes(*args, **kwargs):
        pass

    monkeypatch.setattr(db, "connect", mock_connect)
    monkeypatch.setattr(db, "close", mock_close)
    monkeypatch.setattr(db, "ensure_indexes", mock_ensure_indexes)

    # Seed Default Org and Super Admin
    org = Organization(id="org-test-123", name="Default Organization")
    sync_db["organizations"].insert_one(org.model_dump(mode="json"))

    site = Site(id="site-test-123", organization_id="org-test-123", name="Main Site")
    sync_db["sites"].insert_one(site.model_dump(mode="json"))

    admin = User(
        id="user-admin-123",
        organization_id="org-test-123",
        email="admin@platform.local",
        name="System Super Admin",
        password_hash=hash_password("adminpassword123"),
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    sync_db["users"].insert_one(admin.model_dump(mode="json"))
    yield sync_db


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_auth_headers():
    user = User(
        id="user-admin-123",
        organization_id="org-test-123",
        email="admin@platform.local",
        name="System Super Admin",
        password_hash="...",
        role=UserRole.SUPER_ADMIN,
    )
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}
