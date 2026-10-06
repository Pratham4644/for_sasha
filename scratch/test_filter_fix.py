import asyncio, sys
sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta
from backend.app.db import db
from backend.app.routes.detections import parse_datetime, build_detection_filter
from backend.app.models import User, UserRole

async def test():
    await db.connect()
    # Mock user admin
    admin = User(
        id="test",
        email="admin@test.com",
        name="Admin",
        role=UserRole.SUPER_ADMIN,
        password_hash="dummy",
        organization_id="85dcc187-c43f-44af-974f-bc7fec85b088"
    )

    # Simulate Dashboard query with 7d range
    now = datetime.now(timezone.utc)
    date_from_str = (now - timedelta(days=7)).isoformat()
    print("Testing date_from:", date_from_str)

    # 1. Current build_detection_filter:
    filt_old = build_detection_filter(admin, date_from=date_from_str)
    c_old = await db.detection_events.count_documents(filt_old)
    print("Count with CURRENT build_detection_filter:", c_old)

    # 2. Fixed filter with ISO string:
    dt_from = parse_datetime(date_from_str)
    iso_from = dt_from.isoformat().replace("+00:00", "Z")
    filt_new = {"timestamp": {"$gte": iso_from}}
    c_new = await db.detection_events.count_documents(filt_new)
    print("Count with ISO string filter:", c_new)

    await db.close()

if __name__ == "__main__":
    asyncio.run(test())
