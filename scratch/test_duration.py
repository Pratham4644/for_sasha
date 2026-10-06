import asyncio, sys
sys.path.insert(0, '.')
from datetime import datetime
from collections import defaultdict
from backend.app.db import db

async def test():
    await db.connect()
    # Fetch timestamps grouped by camera
    cursor = db.detection_events.find({}, {'camera_id': 1, 'timestamp': 1}).sort('timestamp', 1).limit(5000)
    docs = [d async for d in cursor]
    
    # Calculate continuous detection sessions (threshold e.g. 5 seconds gap)
    by_cam = defaultdict(list)
    for d in docs:
        ts_val = d.get('timestamp')
        if isinstance(ts_val, str):
            dt = datetime.fromisoformat(ts_val.replace('Z', '+00:00'))
        elif isinstance(ts_val, datetime):
            dt = ts_val
        else:
            continue
        by_cam[d.get('camera_id')].append(dt)
        
    durations = []
    for cid, ts_list in by_cam.items():
        if not ts_list:
            continue
        sess_start = ts_list[0]
        sess_prev = ts_list[0]
        for cur in ts_list[1:]:
            gap = (cur - sess_prev).total_seconds()
            if gap <= 5.0:
                sess_prev = cur
            else:
                dur = max(1.0, (sess_prev - sess_start).total_seconds())
                durations.append(dur)
                sess_start = cur
                sess_prev = cur
        dur = max(1.0, (sess_prev - sess_start).total_seconds())
        durations.append(dur)
        
    print(f"Total sessions: {len(durations)}")
    if durations:
        print(f"Average session duration: {sum(durations)/len(durations):.1f}s")
        print(f"Total session duration: {sum(durations):.1f}s")
        print(f"Max session duration: {max(durations):.1f}s")

    await db.close()

if __name__ == '__main__':
    asyncio.run(test())
