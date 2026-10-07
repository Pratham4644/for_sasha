#!/usr/bin/env python3
"""Create or update an edge gateway token record for remote LAN camera ingestion."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app.auth import hash_edge_token
from backend.app.config import settings
from backend.app.db import db
from backend.app.models import EdgeGateway, utc_now

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("seed-edge-gateway")


async def main() -> None:
    token = os.getenv("EDGE_GATEWAY_TOKEN") or settings.edge_gateway_token
    if not token:
        token = secrets.token_urlsafe(32)
        LOGGER.warning("Generated new EDGE_GATEWAY_TOKEN (store securely): %s", token)

    org_id = os.getenv("EDGE_GATEWAY_ORG_ID") or settings.edge_gateway_org_id
    connected = await db.connect()
    if not connected:
        LOGGER.error("Could not connect to MongoDB.")
        sys.exit(1)

    try:
        await db.ensure_indexes()
        if not org_id:
            org_doc = await db.organizations.find_one({})
            if not org_doc:
                LOGGER.error("No organization found. Run scripts/seed_admin.py first.")
                sys.exit(1)
            org_id = org_doc["id"]

        token_hash = hash_edge_token(token)
        existing = await db.edge_gateways.find_one({"organization_id": org_id, "is_active": True})
        now = utc_now()
        if existing:
            await db.edge_gateways.update_one(
                {"id": existing["id"]},
                {"$set": {"token_hash": token_hash, "updated_at": now}},
            )
            LOGGER.info("Updated edge gateway token for org %s (gateway id=%s)", org_id, existing["id"])
        else:
            gateway = EdgeGateway(
                organization_id=org_id,
                name="Primary Edge Gateway",
                token_hash=token_hash,
            )
            await db.edge_gateways.insert_one(gateway.model_dump(mode="json"))
            LOGGER.info("Created edge gateway for org %s (gateway id=%s)", org_id, gateway.id)

        LOGGER.info("Configure the same token on the edge machine in edge/.env")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
