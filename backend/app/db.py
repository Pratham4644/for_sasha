from __future__ import annotations

import logging
from typing import Any
from pymongo import AsyncMongoClient, ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from backend.app.config import settings

LOGGER = logging.getLogger("camera.platform.db")


class DatabaseConnectionError(Exception):
    """Raised when the database cannot be reached."""
    pass


class Database:
    """Async database client managing MongoDB connections, collections, and indexes."""

    def __init__(self) -> None:
        self.client: AsyncMongoClient | None = None
        self.db: AsyncDatabase | None = None
        self._connected = False

    async def connect(
        self,
        uri: str | None = None,
        database_name: str | None = None,
    ) -> bool:
        """Connects to MongoDB using native AsyncMongoClient with error handling."""
        target_uri = uri or settings.mongodb_uri
        target_db = database_name or settings.mongodb_database
        try:
            self.client = AsyncMongoClient(
                target_uri,
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
                socketTimeoutMS=8000,
                maxPoolSize=25,
            )
            # Verify connectivity
            await self.client.admin.command("ping")
            self.db = self.client[target_db]
            self._connected = True
            LOGGER.info("Successfully connected to MongoDB (%s)", target_db)
            return True
        except Exception as exc:
            LOGGER.error("Failed to connect to MongoDB (%s): %s", target_uri, exc)
            self._connected = False
            return False

    async def close(self) -> None:
        """Closes MongoDB connection."""
        if self.client:
            await self.client.close()
            self._connected = False
            LOGGER.info("Closed MongoDB connection.")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def users(self) -> AsyncCollection:
        if self.db is None:
            raise DatabaseConnectionError("Database not connected")
        return self.db["users"]

    @property
    def cameras(self) -> AsyncCollection:
        if self.db is None:
            raise DatabaseConnectionError("Database not connected")
        return self.db["cameras"]

    @property
    def detection_events(self) -> AsyncCollection:
        if self.db is None:
            raise DatabaseConnectionError("Database not connected")
        return self.db["detection_events"]

    @property
    def sites(self) -> AsyncCollection:
        if self.db is None:
            raise DatabaseConnectionError("Database not connected")
        return self.db["sites"]

    @property
    def organizations(self) -> AsyncCollection:
        if self.db is None:
            raise DatabaseConnectionError("Database not connected")
        return self.db["organizations"]

    @property
    def logs(self) -> AsyncCollection:
        if self.db is None:
            raise DatabaseConnectionError("Database not connected")
        return self.db["logs"]

    @property
    def edge_gateways(self) -> AsyncCollection:
        if self.db is None:
            raise DatabaseConnectionError("Database not connected")
        return self.db["edge_gateways"]

    async def ensure_indexes(self) -> None:
        """Creates required MongoDB indexes across collections."""
        if not self._connected or self.db is None:
            LOGGER.warning("Skipping index creation: MongoDB is not connected.")
            return

        try:
            # 1. Users Indexes
            await self.users.create_indexes([
                IndexModel([("email", ASCENDING)], unique=True, name="idx_users_email_unique"),
                IndexModel([("id", ASCENDING)], unique=True, name="idx_users_id_unique"),
                IndexModel([("organization_id", ASCENDING)], name="idx_users_org"),
            ])

            # 2. Cameras Indexes
            await self.cameras.create_indexes([
                IndexModel([("id", ASCENDING)], unique=True, name="idx_cameras_id_unique"),
                IndexModel([("organization_id", ASCENDING), ("media_path", ASCENDING)], name="idx_cameras_org_mediapath"),
                IndexModel([("organization_id", ASCENDING), ("site_id", ASCENDING)], name="idx_cameras_org_site"),
                IndexModel([("status", ASCENDING)], name="idx_cameras_status"),
            ])

            # 3. Detection Events Indexes (High-Volume Optimization)
            await self.detection_events.create_indexes([
                IndexModel([("id", ASCENDING)], unique=True, name="idx_det_id_unique"),
                IndexModel([("camera_id", ASCENDING), ("timestamp", DESCENDING)], name="idx_det_camera_timestamp"),
                IndexModel([("organization_id", ASCENDING), ("timestamp", DESCENDING)], name="idx_det_org_timestamp"),
                IndexModel([("class_name", ASCENDING)], name="idx_det_class_name"),
                IndexModel([("confidence", ASCENDING)], name="idx_det_confidence"),
                IndexModel([("created_at", DESCENDING)], name="idx_det_created_at"),
                # TTL index for automatic retention expiration
                IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_det_ttl"),
            ])

            # 4. Sites & Organizations Indexes
            await self.sites.create_indexes([
                IndexModel([("id", ASCENDING)], unique=True, name="idx_sites_id_unique"),
                IndexModel([("organization_id", ASCENDING)], name="idx_sites_org"),
            ])
            await self.organizations.create_indexes([
                IndexModel([("id", ASCENDING)], unique=True, name="idx_orgs_id_unique"),
            ])

            # 5. Audit Logs Indexes
            await self.logs.create_indexes([
                IndexModel([("organization_id", ASCENDING), ("created_at", DESCENDING)], name="idx_logs_org_created"),
                IndexModel([("resource_type", ASCENDING)], name="idx_logs_resource_type"),
            ])

            # 6. Edge Gateway Indexes
            await self.edge_gateways.create_indexes([
                IndexModel([("id", ASCENDING)], unique=True, name="idx_edge_gateways_id_unique"),
                IndexModel([("token_hash", ASCENDING)], unique=True, name="idx_edge_gateways_token_hash_unique"),
                IndexModel([("organization_id", ASCENDING)], name="idx_edge_gateways_org"),
            ])

            LOGGER.info("All MongoDB indexes verified and created successfully.")
        except Exception as exc:
            LOGGER.error("Error creating MongoDB indexes: %s", exc)


db = Database()
