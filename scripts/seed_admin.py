#!/usr/bin/env python3
"""
Seed script to create the initial default organization, default site, and Super Admin user.
Idempotent and safe to run repeatedly.
"""
import asyncio
import logging
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app.auth import hash_password
from backend.app.config import settings
from backend.app.db import db
from backend.app.models import Organization, Site, User, UserRole

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("seed")

DEFAULT_ORG_NAME = "Default Organization"
DEFAULT_SITE_NAME = "Main Surveillance Site"
DEFAULT_ADMIN_EMAIL = "admin@platform.local"
DEFAULT_ADMIN_PASSWORD = "adminpassword123"
DEFAULT_ADMIN_NAME = "System Super Admin"


async def main() -> None:
    LOGGER.info("Connecting to MongoDB (%s)...", settings.mongodb_database)
    connected = await db.connect()
    if not connected:
        LOGGER.error("Could not connect to MongoDB. Check MONGODB_URI in .env.")
        sys.exit(1)

    try:
        await db.ensure_indexes()

        # 1. Ensure Default Organization
        org_doc = await db.organizations.find_one({"name": DEFAULT_ORG_NAME})
        if not org_doc:
            org = Organization(name=DEFAULT_ORG_NAME)
            await db.organizations.insert_one(org.model_dump(mode="json"))
            org_id = org.id
            LOGGER.info("Created organization: %s (id: %s)", org.name, org_id)
        else:
            org_id = org_doc["id"]
            LOGGER.info("Found existing organization: %s (id: %s)", org_doc["name"], org_id)

        # 2. Ensure Default Site
        site_doc = await db.sites.find_one({"organization_id": org_id, "name": DEFAULT_SITE_NAME})
        if not site_doc:
            site = Site(organization_id=org_id, name=DEFAULT_SITE_NAME, description="Primary CCTV monitoring site")
            await db.sites.insert_one(site.model_dump(mode="json"))
            site_id = site.id
            LOGGER.info("Created site: %s (id: %s)", site.name, site_id)
        else:
            site_id = site_doc["id"]
            LOGGER.info("Found existing site: %s (id: %s)", site_doc["name"], site_id)

        # 3. Ensure Super Admin
        admin_doc = await db.users.find_one({"email": DEFAULT_ADMIN_EMAIL.lower()})
        if not admin_doc:
            admin = User(
                organization_id=org_id,
                email=DEFAULT_ADMIN_EMAIL.lower(),
                name=DEFAULT_ADMIN_NAME,
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                role=UserRole.SUPER_ADMIN,
                is_active=True,
            )
            await db.users.insert_one(admin.model_dump(mode="json"))
            LOGGER.info("Created Super Admin: %s (password: %s)", DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)
        else:
            LOGGER.info("Super Admin already exists: %s", DEFAULT_ADMIN_EMAIL)

        LOGGER.info("Database seeding complete!")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
