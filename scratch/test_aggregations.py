import asyncio, sys
sys.path.insert(0, '.')
from backend.app.db import db
import time

async def test():
    await db.connect()
    t0 = time.time()
    
    # 1. Total count
    total = await db.detection_events.count_documents({})
    print(f"Total detections: {total}")
    
    # 2. Classes aggregation
    class_pipeline = [
        {"$group": {"_id": "$class_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    cur = await db.detection_events.aggregate(class_pipeline)
    classes = [d async for d in cur]
    print(f"Classes aggregated ({len(classes)} classes):")
    for c in classes[:5]:
        print(f"  {c['_id']}: {c['count']} ({c['count']/total*100:.1f}%)")
        
    # 3. Camera aggregation
    cam_pipeline = [
        {"$group": {
            "_id": "$camera_id",
            "count": {"$sum": 1},
            "last_activity": {"$max": "$timestamp"},
            "camera_name": {"$first": "$camera_name"}
        }},
        {"$sort": {"count": -1}}
    ]
    cur_cam = await db.detection_events.aggregate(cam_pipeline)
    cams = [d async for d in cur_cam]
    print(f"\nCameras aggregated ({len(cams)} cameras):")
    total_cam_dets = sum(c['count'] for c in cams)
    print(f"Sum of camera counts: {total_cam_dets} (matches total: {total_cam_dets == total})")
    for c in cams[:5]:
        print(f"  {c['_id']} ({c.get('camera_name')}): {c['count']} last: {c['last_activity']}")
        
    # 4. Day trends aggregation
    trend_pipeline = [
        {"$group": {
            "_id": {"$substrCP": ["$timestamp", 0, 10]},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    cur_trend = await db.detection_events.aggregate(trend_pipeline)
    trends = [d async for d in cur_trend]
    print(f"\nTrends aggregated ({len(trends)} days):")
    for t in trends:
        print(f"  {t['_id']}: {t['count']}")
        
    print(f"\nAll aggregations completed in {(time.time() - t0)*1000:.1f}ms")
    await db.close()

if __name__ == '__main__':
    asyncio.run(test())
