import asyncio, sys
sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta
from backend.app.db import db
from backend.app.routes.detections import parse_datetime

async def test():
    await db.connect()
    dt_from = parse_datetime("2026-09-29T00:00:00Z")
    iso_from = dt_from.isoformat().replace("+00:00", "Z")

    # Dual condition
    dual_q = {
        "$or": [
            {"timestamp": {"$gte": iso_from}},
            {"timestamp": {"$gte": dt_from}},
        ]
    }
    c_dual = await db.detection_events.count_documents(dual_q)
    print("Dual condition count:", c_dual)

    # String only
    c_str = await db.detection_events.count_documents({"timestamp": {"$gte": iso_from}})
    print("String only count:", c_str)

    await db.close()

if __name__ == "__main__":
    asyncio.run(test())
