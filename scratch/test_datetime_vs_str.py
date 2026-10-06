import asyncio, sys
sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta
from backend.app.db import db
from backend.app.routes.detections import parse_datetime

async def test():
    await db.connect()
    dt_from = parse_datetime("2026-09-29T00:00:00Z")
    print("Parsed dt_from:", repr(dt_from), type(dt_from))

    # Test 1: querying with datetime object
    c_dt = await db.detection_events.count_documents({"timestamp": {"$gte": dt_from}})
    print("Query with datetime object:", c_dt)

    # Test 2: querying with ISO string
    iso_str = dt_from.isoformat().replace("+00:00", "Z")
    c_str = await db.detection_events.count_documents({"timestamp": {"$gte": iso_str}})
    print("Query with ISO string:", c_str)

    await db.close()

if __name__ == "__main__":
    asyncio.run(test())
