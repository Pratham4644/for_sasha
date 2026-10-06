import asyncio
from backend.app.db import db
from datetime import datetime, timezone, timedelta

async def check():
    await db.connect()
    cursor = db.detection_events.find({}, {"timestamp": 1, "_id": 0}).limit(5)
    docs = [d async for d in cursor]
    print("Sample timestamps:", docs)

    c_all = await db.detection_events.count_documents({})
    print("Total events:", c_all)

    c_date = await db.detection_events.count_documents({"timestamp": {"$type": "date"}})
    print("BSON date count:", c_date)

    c_str = await db.detection_events.count_documents({"timestamp": {"$type": "string"}})
    print("BSON string count:", c_str)

    # Test query with ISO string
    past_7d_str = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    print("Querying >= past_7d_str:", past_7d_str)
    c_str_query = await db.detection_events.count_documents({"timestamp": {"$gte": past_7d_str}})
    print("Count with $gte string:", c_str_query)

    # Test query with datetime object
    past_7d_dt = datetime.now(timezone.utc) - timedelta(days=7)
    c_dt_query = await db.detection_events.count_documents({"timestamp": {"$gte": past_7d_dt}})
    print("Count with $gte datetime:", c_dt_query)

    await db.close()

if __name__ == "__main__":
    asyncio.run(check())
