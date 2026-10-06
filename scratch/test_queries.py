import asyncio, sys
sys.path.insert(0, '.')
from backend.app.db import db
import json

async def test():
    await db.connect()
    with_det = await db.detection_events.count_documents({"detections": {"$exists": True, "$ne": []}})
    print("Events with non-empty detections list:", with_det)
    sample = await db.detection_events.find_one({"detections": {"$exists": True, "$ne": []}})
    if sample:
        sample["_id"] = str(sample["_id"])
        print("Sample with detections list:")
        print(json.dumps(sample, indent=2, default=str))
    
    # Also look at samples without non-empty detections list
    sample_empty = await db.detection_events.find_one({"detections": []})
    if sample_empty:
        sample_empty["_id"] = str(sample_empty["_id"])
        print("\nSample with empty detections list:")
        print(json.dumps(sample_empty, indent=2, default=str))

    # Let's inspect multiple recent docs to see timestamps and grouping
    cursor = db.detection_events.find({}).sort("timestamp", -1).limit(20)
    docs = [d async for d in cursor]
    print("\nRecent 20 docs timestamps and camera_ids:")
    for d in docs:
        print(f"cam={d.get('camera_id')} name={d.get('camera_name')} ts={d.get('timestamp')} class={d.get('class_name')} det_count={len(d.get('detections', []))}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(test())
